"""
PageController Module
Encapsulates all complex logic for direct interaction with Playwright pages.
"""

import asyncio
import random
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Page as AsyncPage
from playwright.async_api import expect as expect_async

from config import (
    CLEAR_CHAT_BUTTON_SELECTOR,
    CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR,
    CLICK_TIMEOUT_MS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_STOP_SEQUENCES,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    EDIT_MESSAGE_BUTTON_SELECTOR,
    ENABLE_URL_CONTEXT,
    PROMPT_TEXTAREA_SELECTOR,
    SUBMIT_BUTTON_SELECTOR,
    UPLOAD_BUTTON_SELECTOR,
)
from models import ClientDisconnectedError, QuotaExceededError

from .initialization import enable_temporary_chat_mode
from .operations import (
    _get_final_response_content,
    _wait_for_response_completion,
    check_quota_limit,
    get_response_via_copy_button,
    get_response_via_edit_button,
)
from .page_controller_modules.base import BaseController
from .page_controller_modules.chat import ChatController
from .page_controller_modules.function_calling import FunctionCallingController
from .page_controller_modules.input import InputController
from .page_controller_modules.parameters import ParameterController
from .page_controller_modules.response import ResponseController
from .page_controller_modules.thinking import ThinkingController


class PageController(
    ParameterController,
    InputController,
    ChatController,
    ResponseController,
    ThinkingController,
    FunctionCallingController,
    BaseController,
):
    """Encapsulates all operations for interacting with the AI Studio page."""

    def __init__(self, page: AsyncPage, logger, req_id: str):
        self.page = page
        self.logger = logger
        self.req_id = req_id

    async def _check_disconnect(self, check_client_disconnected: Callable, stage: str):
        if check_client_disconnected(stage):
            raise ClientDisconnectedError(
                f"[{self.req_id}] Client disconnected at stage: {stage}"
            )

    async def adjust_parameters(
        self,
        request_params: Dict[str, Any],
        page_params_cache: Dict[str, Any],
        params_cache_lock: asyncio.Lock,
        model_id_to_use: Optional[str],
        parsed_model_list: List[Dict[str, Any]],
        check_client_disconnected: Callable,
        is_streaming: bool = True,
    ):
        self.logger.info(f"[{self.req_id}] Adjusting parameters...")
        await self._check_disconnect(
            check_client_disconnected, "Start Parameter Adjustment"
        )

        _t_params = time.perf_counter()

        # These four controls live inside the collapsible "Advanced settings"
        # section. When it is collapsed they are not in the DOM at all, so each
        # adjustment burns a 5s visibility timeout plus a diagnostic snapshot
        # before failing - measured ~20s of dead time per request, which is the
        # bulk of the proxy's latency. Probe/expand once, skip the group if it
        # is genuinely unavailable and keep the page's current values.
        advanced_ok = await self._ensure_advanced_settings_expanded()
        self.logger.info(
            f"[{self.req_id}] [Timing] params_probe={time.perf_counter() - _t_params:.2f}s "
            f"advanced={advanced_ok}"
        )
        if advanced_ok:
            temp = request_params.get("temperature", DEFAULT_TEMPERATURE)
            await self._adjust_temperature(
                temp, page_params_cache, params_cache_lock, check_client_disconnected
            )
            max_tokens = request_params.get(
                "max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS
            )
            await self._adjust_max_tokens(
                max_tokens,
                page_params_cache,
                params_cache_lock,
                model_id_to_use,
                parsed_model_list,
                check_client_disconnected,
            )
            stop = request_params.get("stop", DEFAULT_STOP_SEQUENCES)
            await self._adjust_stop_sequences(
                stop, page_params_cache, params_cache_lock, check_client_disconnected
            )
            top_p = request_params.get("top_p", DEFAULT_TOP_P)
            await self._adjust_top_p(top_p, check_client_disconnected)
        else:
            self.logger.debug(
                f"[{self.req_id}] Advanced settings section unavailable; keeping "
                "the page's current temperature/top_p/stop values."
            )

        self.logger.info(
            f"[{self.req_id}] [Timing] params_total={time.perf_counter() - _t_params:.2f}s"
        )

        await self._ensure_tools_panel_expanded(check_client_disconnected)

        # Force disable URL context if function calling is active
        is_fc_enabled = await self.is_function_calling_enabled(
            check_client_disconnected
        )
        if is_fc_enabled:
            await self._adjust_url_context(False, check_client_disconnected)
        elif ENABLE_URL_CONTEXT:
            await self._adjust_url_context(True, check_client_disconnected)

        await self._handle_thinking_budget(
            request_params,
            page_params_cache,
            params_cache_lock,
            model_id_to_use,
            check_client_disconnected,
            is_streaming,
        )
        await self._adjust_google_search(
            request_params, model_id_to_use, check_client_disconnected
        )

    async def clear_chat_history(self, check_client_disconnected: Callable):
        """Clear chat history and invalidate function calling cache."""
        self.logger.info(f"[{self.req_id}] Clearing chat history...")

        # Invalidate FC cache since we're starting a new chat
        self.invalidate_fc_cache("new_chat")

        btn = self.page.locator(CLEAR_CHAT_BUTTON_SELECTOR)
        if await btn.is_enabled(timeout=5000):
            await btn.click(timeout=CLICK_TIMEOUT_MS)
            confirm = self.page.locator(CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR)
            if await confirm.is_visible(timeout=2000):
                await confirm.click(timeout=CLICK_TIMEOUT_MS)
            await enable_temporary_chat_mode(self.page)

    async def _model_is_locked(self) -> bool:
        """
        True when AI Studio refuses to use the selected model for this account.

        Some models appear in the ListModels response but require a paid plan or
        an API key. The UI then replaces the chat pane with "Upgrade to unlock
        <model>" and disables the prompt editor, so typing silently produces
        nothing and the submit click is inert. Without this check the request
        waits out the full completion timeout (~10 min) and looks like a hang.
        """
        try:
            editor = self.page.locator(PROMPT_TEXTAREA_SELECTOR).first
            if await editor.count() > 0:
                # Fast path: the lock manifests as a disabled/readonly editor.
                # Returning early keeps this to two round trips per request.
                if await editor.is_disabled():
                    return True
                if (await editor.get_attribute("readonly")) is not None:
                    return True
                return False

            # No editor at all: the upgrade wall may have replaced the pane.
            banner = self.page.get_by_text("Upgrade to unlock", exact=False)
            count = await banner.count()
            for i in range(min(count, 2)):
                if await banner.nth(i).is_visible():
                    return True
        except Exception:
            pass
        return False

    async def submit_prompt(
        self, prompt: str, image_list: List, check_client_disconnected: Callable
    ):
        """Submit prompt to the page with retries and keyboard fallbacks."""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                self.logger.info(
                    f"[{self.req_id}] Filling and submitting prompt (Attempt {attempt + 1}/{max_retries})..."
                )
                _stage_t = time.perf_counter()
                _marks: List[str] = []

                def _mark(label: str) -> None:
                    nonlocal _stage_t
                    now = time.perf_counter()
                    _marks.append(f"{label}={now - _stage_t:.2f}")
                    _stage_t = now

                textarea = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
                await expect_async(textarea).to_be_visible(timeout=10000)
                _mark("visible")
                await self._check_disconnect(
                    check_client_disconnected, "After Input Visible"
                )

                # A fresh session opens with an upsell dialog whose blurred
                # backdrop captures every pointer event, so Run never enables
                # and clicks land on the backdrop. Escape is ignored
                # (disableClose) - the header close button is the only exit.
                from .overlays import dismiss_blocking_dialogs

                if await dismiss_blocking_dialogs(self.page, self.logger):
                    self.logger.info(
                        f"[{self.req_id}] Dismissed blocking dialog before submit."
                    )

                # Fail fast instead of waiting out the completion timeout when
                # the selected model is gated for this account.
                if await self._model_is_locked():
                    raise RuntimeError(
                        "Selected model is not available for this account: AI "
                        "Studio is showing an 'Upgrade to unlock' wall and has "
                        "disabled the prompt editor. Use /v1/models to pick a "
                        "model the account can actually run."
                    )
                _mark("overlays")

                # Human-plausible entry: real key events for short prompts, the
                # paste/IME primitive for long ones. Verifies the field readback
                # and only degrades to raw value assignment if both paths fail.
                from .human_input import insert_prompt_text

                if not await insert_prompt_text(
                    self.page, textarea, prompt, self.logger
                ):
                    self.logger.warning(
                        f"[{self.req_id}] Prompt entry could not be verified "
                        "after all strategies; submitting anyway."
                    )
                await self._check_disconnect(
                    check_client_disconnected, "After Input Fill"
                )
                _mark("fill")

                if image_list:
                    await self._open_upload_menu_and_choose_file(image_list)

                # Wait for the submit button to become enabled. Poll instead of
                # a single expect(): the upsell dialog can mount *after* the
                # prompt is filled, and while it is open the Run control is
                # aria-disabled. Dismissing it inside the loop means the control
                # recovers without burning a retry.
                submit = self.page.locator(SUBMIT_BUTTON_SELECTOR)
                button_clicked = False
                is_btn_enabled = False
                enable_deadline = asyncio.get_event_loop().time() + 15
                while asyncio.get_event_loop().time() < enable_deadline:
                    await self._check_disconnect(
                        check_client_disconnected, "Waiting for Submit Button"
                    )
                    try:
                        if await submit.first.is_enabled(timeout=400):
                            is_btn_enabled = True
                            break
                    except Exception:
                        pass

                    if await dismiss_blocking_dialogs(self.page, self.logger):
                        self.logger.info(
                            f"[{self.req_id}] Dismissed blocking dialog while "
                            "waiting for Run to enable."
                        )
                    await asyncio.sleep(0.12)

                if not is_btn_enabled:
                    self.logger.warning(
                        f"[{self.req_id}] Submit button not enabled within timeout, trying keyboard fallback."
                    )

                await self._check_disconnect(
                    check_client_disconnected, "After Submit Button Check"
                )
                _mark("runable")

                if is_btn_enabled:
                    try:
                        # Defensive workarounds before click: handle dialogs, backdrops and tooltips
                        await self._handle_post_upload_dialog()
                        await self._dismiss_backdrops()
                        if hasattr(self, "_dismiss_tooltip_overlays"):
                            await self._dismiss_tooltip_overlays()
                        # Re-check immediately before clicking: a dialog can
                        # mount during parameter adjustment.
                        await dismiss_blocking_dialogs(self.page, self.logger)
                        _mark("prep")

                        # Humans pause between finishing a thought and hitting Run.
                        await asyncio.sleep(random.uniform(0.12, 0.45))
                        _mark("pause")
                        await submit.click(timeout=5000)
                        button_clicked = True
                        _mark("click")
                        self.logger.info(f"[{self.req_id}] Submit button clicked.")
                        self.logger.info(
                            f"[{self.req_id}] [Timing] submit {' '.join(_marks)}"
                        )
                        await check_quota_limit(self.page, self.req_id)
                    except QuotaExceededError:
                        raise
                    except Exception as click_err:
                        self.logger.warning(
                            f"[{self.req_id}] Button click failed: {click_err}. Trying keyboard fallback."
                        )

                if not button_clicked:
                    # Keyboard fallbacks (using logic inherited from InputController)
                    self.logger.info(
                        f"[{self.req_id}] Attempting Enter key submission..."
                    )
                    if await self._try_enter_submit(
                        textarea, check_client_disconnected
                    ):
                        button_clicked = True
                    else:
                        self.logger.info(
                            f"[{self.req_id}] Attempting Combo key submission..."
                        )
                        if await self._try_combo_submit(
                            textarea, check_client_disconnected
                        ):
                            button_clicked = True

                if not button_clicked:
                    raise Exception(
                        "Failed to submit prompt via button or keyboard shortcuts."
                    )

                await self._check_disconnect(check_client_disconnected, "After Submit")
                return
            except QuotaExceededError:
                raise
            except Exception as e:
                self.logger.warning(
                    f"[{self.req_id}] Error during submit (Attempt {attempt + 1}): {e}"
                )
                if attempt < max_retries - 1:
                    await self._safe_reload_page()
                    await asyncio.sleep(2)
                else:
                    raise e

    async def _open_upload_menu_and_choose_file(self, files_list: List[str]) -> bool:
        """Upload files via menu."""
        await self.page.locator(UPLOAD_BUTTON_SELECTOR).first.click()
        btn = self.page.locator("div[role='menu'] button[role='menuitem']").filter(
            has_text="Upload File"
        )
        if await btn.count() == 0:
            btn = self.page.locator("div[role='menu'] button[role='menuitem']").filter(
                has_text="Upload a file"
            )
        async with self.page.expect_file_chooser() as fc_info:
            await btn.first.click()
        await (await fc_info.value).set_files(files_list)
        return True

    async def _safe_reload_page(self):
        """Reload page safely."""
        await self.page.reload(timeout=30000)
        await self.page.wait_for_load_state("domcontentloaded", timeout=30000)

    async def get_response(
        self,
        check_client_disconnected: Callable,
        prompt_length: int = 0,
        timeout: Optional[float] = None,
    ) -> str:
        """Retrieve response content."""
        submit_btn = self.page.locator(SUBMIT_BUTTON_SELECTOR)
        edit_btn = self.page.locator(EDIT_MESSAGE_BUTTON_SELECTOR)
        input_field = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
        await _wait_for_response_completion(
            self.page,
            input_field,
            submit_btn,
            edit_btn,
            self.req_id,
            check_client_disconnected,
            None,
            prompt_length=prompt_length,
            timeout=timeout,
        )
        content = await _get_final_response_content(
            self.page, self.req_id, check_client_disconnected
        )
        if not content or not content.strip():
            verified = await self.verify_response_integrity(check_client_disconnected)
            return verified.get("content", "")
        return content

    async def verify_response_integrity(
        self, check_client_disconnected: Callable, trigger_reason: str = ""
    ) -> Dict[str, str]:
        """Verify integrity via DOM."""
        await asyncio.sleep(1)
        final = await self._extract_complete_response_content()
        content, reasoning = self._separate_thinking_and_response(final)
        return {"content": content, "reasoning_content": reasoning}

    async def get_response_with_integrity_check(
        self,
        check_client_disconnected: Callable,
        prompt_length: int = 0,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Retrieve response content with full integrity check and function calls."""
        content = await self.get_response(
            check_client_disconnected, prompt_length, timeout
        )

        # Parse function calls from DOM as well
        has_fc, function_calls, text_content = await self.parse_function_calls(
            check_client_disconnected
        )

        c, r = self._separate_thinking_and_response(content)

        result = {
            "content": c,
            "reasoning_content": r,
            "recovery_method": "direct",
            "has_function_calls": has_fc,
            "function_calls": function_calls,
        }

        if has_fc:
            # If function calls found, use the text content (with calls removed) as content
            # But we need to separate thinking from it too
            c_fc, r_fc = self._separate_thinking_and_response(text_content)
            result["content"] = c_fc
            # Keep original reasoning if not found in text_content
            if r_fc:
                result["reasoning_content"] = r_fc

        return result

    def _separate_thinking_and_response(self, content: str) -> Tuple[str, str]:
        """Separate thinking and response."""
        if not content:
            return "", ""
        m = re.findall(r"\[THINKING\](.*?)\[/THINKING\]", content, re.DOTALL)
        r = "\n".join(m).strip()
        c = re.sub(
            r"\[THINKING\](.*?)\[/THINKING\]", "", content, flags=re.DOTALL
        ).strip()
        return c, r

    async def _emergency_stability_wait(
        self, check_client_disconnected: Callable
    ) -> bool:
        """Wait for DOM stability."""
        await asyncio.sleep(2)
        return True

    async def _check_generation_activity(self) -> bool:
        """Check if generation is in progress."""
        stop_btn = self.page.locator('button[aria-label="Stop generating"]')
        return await stop_btn.is_visible(timeout=500)

    async def _extract_dom_content(self) -> str:
        """Extract content from DOM."""
        from config.selectors import FINAL_RESPONSE_SELECTOR

        elem = self.page.locator(FINAL_RESPONSE_SELECTOR).last
        return await elem.inner_text() if await elem.count() > 0 else ""

    async def _extract_complete_response_content(self) -> str:
        """Extract complete response content."""
        c = await get_response_via_edit_button(self.page, self.req_id, lambda x: None)
        if not c:
            c = await get_response_via_copy_button(
                self.page, self.req_id, lambda x: None
            )
        return c if c else await self._extract_dom_content()

    async def get_body_text_only_from_dom(self) -> str:
        """Extract body text only."""
        return await self._extract_dom_content()
