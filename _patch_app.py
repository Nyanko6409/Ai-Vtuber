p = 'ai_vtuber/core/app.py'
s = open(p).read()

def rep(old, new):
    global s
    assert old in s, f"MISSING: {old[:80]!r}"
    s = s.replace(old, new, 1)

# 1. imports
rep("from ..emotion.analyzer import analyze_response\n",
    "from ..emotion.analyzer import analyze_response\n"
    "from ..avatar.avatar_control import (\n"
    "    AvatarController,\n"
    "    build_avatar_system_instruction,\n"
    "    parse_avatar_response,\n"
    ")\n")

# 2. avatar_controller property
rep("""    @property
    def microphone(self) -> Microphone:""",
    '''    @property
    def avatar_controller(self) -> AvatarController:
        """Structured avatar-action controller (single Live2D control path)."""
        if self._avatar_controller is None:
            self._avatar_controller = AvatarController(self.avatar)
        return self._avatar_controller

    @property
    def microphone(self) -> Microphone:''')

# 3. init field
rep("        self._avatar: Optional[Live2DAvatar] = None\n",
    "        self._avatar: Optional[Live2DAvatar] = None\n"
    "        self._avatar_controller: Optional[AvatarController] = None\n")

# 4a. soul prompt refresh (non-streaming)
rep("""            # Refresh soul prompt from memory manager before each turn
            # so any newly consolidated memories are reflected immediately.
            self.conversation.set_soul_prompt(self.memory_manager.get_full_context())""",
    r'''            # Refresh soul prompt from memory manager before each turn
            # so any newly consolidated memories are reflected immediately.
            # The structured avatar_action contract + current body state ride
            # along so the LLM emits canonical semantic IDs, not [mood] tags.
            soul = self.memory_manager.get_full_context()
            if self._avatar:
                try:
                    ctrl = self.avatar_controller
                    soul = soul + "\n\n" + build_avatar_system_instruction(ctrl) \
                        + "\n\n" + ctrl.describe_state()
                except Exception as e:
                    logger.warning(f"Avatar instruction injection failed: {e}")
            self.conversation.set_soul_prompt(soul)''')

# 4b. soul prompt refresh (streaming)
rep("""            # Refresh soul prompt before generating
            self.conversation.set_soul_prompt(self.memory_manager.get_full_context())""",
    r'''            # Refresh soul prompt before generating (avatar contract + state)
            soul = self.memory_manager.get_full_context()
            if self._avatar:
                try:
                    ctrl = self.avatar_controller
                    soul = soul + "\n\n" + build_avatar_system_instruction(ctrl) \
                        + "\n\n" + ctrl.describe_state()
                except Exception as e:
                    logger.warning(f"Avatar instruction injection failed: {e}")
            self.conversation.set_soul_prompt(soul)''')

# 5. _generate_response: parse avatar action first
rep("""            # Use the new emotion/topic analyzer
            analysis = analyze_response(raw_response)

            # Extract emotion and cleaned text
            emotion = analysis.emotion
            response_text = analysis.cleaned_text""",
    """            # Split structured avatar_action from spoken text BEFORE anything
            # else sees the reply (TTS/UI/history never receive the JSON block).
            parsed = parse_avatar_response(raw_response)
            self._apply_avatar_action(parsed.avatar_action)

            # Emotion analysis runs on the CLEAN speech text only; emotion is
            # metadata (UI/memory/logging) and no longer drives Live2D.
            analysis = analyze_response(parsed.speech)

            # Extract emotion and cleaned text
            emotion = analysis.emotion
            response_text = analysis.cleaned_text or parsed.speech""")

# 6a. remove emotion->Live2D in voice pipeline
rep('''            logger.debug(f"Response emotion: {emotion}")

            # Update avatar expression (already done in streaming path, but needed for non-streaming)
            if self._avatar and not stream_enabled:
                self.avatar.set_expression(emotion)

            # Speak''',
    '''            logger.debug(f"Response emotion: {emotion} (metadata only; Live2D is driven by avatar_action)")

            # Speak''')

# 6b. remove neutral reset (voice pipeline non-streaming speak)
rep('''                if self._avatar:
                    self.avatar.set_talking(False)
                    self.avatar.set_expression("neutral")
                    logger.debug("Avatar speaking finished, expression reset to neutral")''',
    '''                if self._avatar:
                    self.avatar.set_talking(False)
                    # NOTE: expression/items intentionally persist until another
                    # avatar_action changes them - no automatic neutral reset.''')

# 7a. streaming guard var
rep("            # Queue for sending sentences to TTS producer (includes emotion context)",
    '''            # Streaming guard: never feed a partial/complete avatar JSON block
            # to TTS. Buffer tokens containing the block until the full reply
            # is in; the action is parsed/applied exactly once afterwards.
            pending_action_text = ""

            # Queue for sending sentences to TTS producer (includes emotion context)''')

# 7b. sentence loop: hold back JSON fragments
QUOTE = '"'
rep("""                    if sentence:
                        # Strip emotion tag from first sentence if present
                        # (same logic as non-streaming path via analyze_response/cleaned_text)
                        if raw_response.startswith('['):
                            first_line = raw_response.split('\\n')[0]
                            if first_line.startswith('[') and first_line.endswith(']'):
                                # This is the first sentence and has an emotion tag prefix
                                # The tag will be stripped by normalize_text before TTS, same as non-streaming
                                pass  # normalize_text handles tag stripping

                        try:""",
    "                    if " + repr(QUOTE + "avatar_action" + QUOTE) + " in pending_action_text + sentence:\n"
    "                        # This sentence belongs (fully or partly) to the\n"
    "                        # avatar JSON block - hold it back from TTS entirely.\n"
    '                        pending_action_text += (" " if pending_action_text else "") + sentence\n'
    "                        continue\n"
    "                    if pending_action_text:\n"
    "                        # Block still streaming in; keep buffering until the\n"
    "                        # final flush below (never emit half-written JSON).\n"
    '                        pending_action_text += " " + sentence\n'
    "                        continue\n"
    "\n"
    "                    if sentence:\n"
    "                        try:")

# 7c. tail buffer flush routes JSON away from TTS
rep('''            # Handle any remaining text in buffer
            if token_buffer.strip():
                try:
                    tts_input_queue.put((token_buffer.strip(), "neutral"), block=False)
                except queue.Full:
                    logger.warning("TTS input queue full, dropping final text")''',
    '''            # Handle any remaining text in buffer - but route anything that
            # contains the avatar JSON block to the parser, not to TTS.
            tail = token_buffer.strip()
            if tail:
                if AVATAR_KEY_MARK in pending_action_text + tail:
                    pending_action_text += (" " if pending_action_text else "") + tail
                elif pending_action_text:
                    pending_action_text += " " + tail
                else:
                    try:
                        tts_input_queue.put((tail, "neutral"), block=False)
                    except queue.Full:
                        logger.warning("TTS input queue full, dropping final text")''')
# define the marker constant right after the guard var
rep('            pending_action_text = ""\n',
    '            pending_action_text = ""\n'
    '            AVATAR_KEY_MARK = \'"avatar_action"\'\n')

# 8. streaming post-processing: parse once complete
rep("""            # Now run emotion analysis on full response
            analysis = analyze_response(raw_response)
            emotion = analysis.emotion
            response_text = analysis.cleaned_text""",
    """            # Parse the structured avatar action ONCE the full reply is in
            # (raw_response contains everything streamed, including the block).
            parsed = parse_avatar_response(raw_response)
            self._apply_avatar_action(parsed.avatar_action)

            # Now run emotion analysis on the clean spoken text only
            analysis = analyze_response(parsed.speech)
            emotion = analysis.emotion
            response_text = analysis.cleaned_text or parsed.speech""")

# 9. streaming on_playback_end neutral reset
rep('''                if self._avatar:
                    logger.debug("TTS playback finished")
                    self.avatar.set_talking(False)
                    self.avatar.set_expression("neutral")''',
    '''                if self._avatar:
                    logger.debug("TTS playback finished")
                    self.avatar.set_talking(False)
                    # Expression/items persist until the next avatar_action.''')

# 10a. chat worker: emotion no longer drives Live2D
rep('''            # Update avatar expression
            if self._avatar:
                self.avatar.set_expression(emotion)
                self.avatar.set_talking(True)''',
    '''            # Avatar face/items were already applied via avatar_action inside
            # _generate_response(); emotion here is UI/log metadata only.
            if self._avatar:
                self.avatar.set_talking(True)''')

# 10b. chat worker: no neutral reset
rep('''            # Done speaking
            if self._avatar:
                self.avatar.set_talking(False)
                self.avatar.set_expression("neutral")''',
    '''            # Done speaking
            if self._avatar:
                self.avatar.set_talking(False)
                # No neutral reset: actions persist until the next avatar_action.''')

# 11. helper method
rep('''    def _speak(self, text: str) -> None:
        """Generate and play TTS audio with lip sync."""''',
    '''    def _apply_avatar_action(self, action: Optional[dict]) -> None:
        """Apply one parsed avatar_action through AvatarController (only Live2D path)."""
        if action is None:
            logger.debug("Avatar action: none in this response (state unchanged)")
            return
        if not self._avatar:
            logger.debug(f"Avatar action (no avatar loaded, dropped): {action}")
            return
        expr = action.get("expression")
        items_on = action.get("items_add") or action.get("items_on") or []
        items_off = action.get("items_remove") or action.get("items_off") or []
        modes_on = action.get("modes_on") or []
        modes_off = action.get("modes_off") or []
        logger.info(
            "Avatar action: expression=%s items_on=%s items_off=%s modes_on=%s modes_off=%s",
            expr, items_on, items_off, modes_on, modes_off,
        )
        try:
            report = self.avatar_controller.apply_avatar_action(action)
            if report.get("expression_set"):
                logger.info("Expression applied: %s", report["expression_set"])
            for item in report.get("added", []):
                logger.info("Item enabled: %s", item)
            for item in report.get("removed", []):
                logger.info("Item disabled: %s", item)
            for bad in report.get("rejected", []):
                logger.warning("Unsupported avatar id %r; ignoring", bad)
        except Exception as e:
            logger.warning(f"Avatar action failed (conversation continues): {e}")

    def _speak(self, text: str) -> None:
        """Generate and play TTS audio with lip sync."""''')

open(p, 'w').write(s)
print("app.py written OK")
