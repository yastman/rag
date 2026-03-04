"""Unit tests for CallbackData factories (#785)."""

from __future__ import annotations


class TestFeedbackCB:
    def test_like_pack_format(self):
        from telegram_bot.callback_data import FeedbackCB

        packed = FeedbackCB(action="like", trace_id="abc123def456").pack()
        assert packed == "fb:like:abc123def456"

    def test_dislike_pack_format(self):
        from telegram_bot.callback_data import FeedbackCB

        packed = FeedbackCB(action="dislike", trace_id="abc123def456").pack()
        assert packed == "fb:dislike:abc123def456"

    def test_done_pack_format(self):
        from telegram_bot.callback_data import FeedbackCB

        packed = FeedbackCB(action="done", trace_id="").pack()
        assert packed.startswith("fb:done:")

    def test_unpack_like(self):
        from telegram_bot.callback_data import FeedbackCB

        cb = FeedbackCB.unpack("fb:like:abc123def456")
        assert cb.action == "like"
        assert cb.trace_id == "abc123def456"

    def test_unpack_dislike(self):
        from telegram_bot.callback_data import FeedbackCB

        cb = FeedbackCB.unpack("fb:dislike:trace999")
        assert cb.action == "dislike"
        assert cb.trace_id == "trace999"

    def test_roundtrip(self):
        from telegram_bot.callback_data import FeedbackCB

        original = FeedbackCB(action="like", trace_id="trace_xyz")
        unpacked = FeedbackCB.unpack(original.pack())
        assert unpacked.action == original.action
        assert unpacked.trace_id == original.trace_id

    def test_packed_within_64_bytes(self):
        from telegram_bot.callback_data import FeedbackCB

        trace_id = "a" * 32
        for action in ("like", "dislike"):
            packed = FeedbackCB(action=action, trace_id=trace_id).pack()
            assert len(packed.encode()) <= 64


class TestFeedbackReasonCB:
    def test_pack_format(self):
        from telegram_bot.callback_data import FeedbackReasonCB

        packed = FeedbackReasonCB(code="wt", trace_id="abc123").pack()
        assert packed == "fbr:wt:abc123"

    def test_unpack(self):
        from telegram_bot.callback_data import FeedbackReasonCB

        cb = FeedbackReasonCB.unpack("fbr:ha:trace999")
        assert cb.code == "ha"
        assert cb.trace_id == "trace999"

    def test_all_reason_codes_pack_within_64_bytes(self):
        from telegram_bot.callback_data import FeedbackReasonCB

        trace_id = "a" * 32
        for code in ("wt", "mi", "bs", "ha", "ic", "fm"):
            packed = FeedbackReasonCB(code=code, trace_id=trace_id).pack()
            assert len(packed.encode()) <= 64

    def test_roundtrip(self):
        from telegram_bot.callback_data import FeedbackReasonCB

        original = FeedbackReasonCB(code="bs", trace_id="trace_abc")
        unpacked = FeedbackReasonCB.unpack(original.pack())
        assert unpacked.code == original.code
        assert unpacked.trace_id == original.trace_id

    def test_prefix_is_fbr(self):
        from telegram_bot.callback_data import FeedbackReasonCB

        packed = FeedbackReasonCB(code="fm", trace_id="trace_xyz").pack()
        assert packed.startswith("fbr:")


class TestFavoriteCB:
    def test_add_pack_format(self):
        from telegram_bot.callback_data import FavoriteCB

        packed = FavoriteCB(action="add", apartment_id="prop-42").pack()
        assert packed == "fav:add:prop-42"

    def test_remove_pack_format(self):
        from telegram_bot.callback_data import FavoriteCB

        packed = FavoriteCB(action="remove", apartment_id="prop-42").pack()
        assert packed == "fav:remove:prop-42"

    def test_viewing_pack_format(self):
        from telegram_bot.callback_data import FavoriteCB

        packed = FavoriteCB(action="viewing", apartment_id="prop-42").pack()
        assert packed == "fav:viewing:prop-42"

    def test_viewing_all_pack_format(self):
        from telegram_bot.callback_data import FavoriteCB

        packed = FavoriteCB(action="viewing_all", apartment_id="").pack()
        assert packed.startswith("fav:viewing_all:")

    def test_unpack_add(self):
        from telegram_bot.callback_data import FavoriteCB

        cb = FavoriteCB.unpack("fav:add:prop-99")
        assert cb.action == "add"
        assert cb.apartment_id == "prop-99"

    def test_unpack_remove(self):
        from telegram_bot.callback_data import FavoriteCB

        cb = FavoriteCB.unpack("fav:remove:prop-99")
        assert cb.action == "remove"
        assert cb.apartment_id == "prop-99"

    def test_roundtrip(self):
        from telegram_bot.callback_data import FavoriteCB

        original = FavoriteCB(action="add", apartment_id="some-prop-id")
        unpacked = FavoriteCB.unpack(original.pack())
        assert unpacked.action == original.action
        assert unpacked.apartment_id == original.apartment_id


class TestResultsCB:
    def test_more_pack_format(self):
        from telegram_bot.callback_data import ResultsCB

        packed = ResultsCB(action="more").pack()
        assert packed == "results:more"

    def test_refine_pack_format(self):
        from telegram_bot.callback_data import ResultsCB

        packed = ResultsCB(action="refine").pack()
        assert packed == "results:refine"

    def test_viewing_pack_format(self):
        from telegram_bot.callback_data import ResultsCB

        packed = ResultsCB(action="viewing").pack()
        assert packed == "results:viewing"

    def test_unpack_more(self):
        from telegram_bot.callback_data import ResultsCB

        cb = ResultsCB.unpack("results:more")
        assert cb.action == "more"

    def test_roundtrip(self):
        from telegram_bot.callback_data import ResultsCB

        for action in ("more", "refine", "viewing"):
            original = ResultsCB(action=action)
            unpacked = ResultsCB.unpack(original.pack())
            assert unpacked.action == original.action


class TestParseFeedbackCallbackNewFormat:
    """Tests for parse_feedback_callback with new CallbackData format."""

    def test_parses_like_new_format(self):
        from telegram_bot.callback_data import FeedbackCB
        from telegram_bot.feedback import parse_feedback_callback

        packed = FeedbackCB(action="like", trace_id="abc123def456").pack()
        result = parse_feedback_callback(packed)
        assert result == (1.0, "abc123def456", None)

    def test_parses_dislike_new_format(self):
        from telegram_bot.callback_data import FeedbackCB
        from telegram_bot.feedback import parse_feedback_callback

        packed = FeedbackCB(action="dislike", trace_id="abc123def456").pack()
        result = parse_feedback_callback(packed)
        assert result == (0.0, "abc123def456", None)

    def test_parses_reason_new_format(self):
        from telegram_bot.callback_data import FeedbackReasonCB
        from telegram_bot.feedback import parse_feedback_callback

        packed = FeedbackReasonCB(code="wt", trace_id="abc123").pack()
        result = parse_feedback_callback(packed)
        assert result == (0.0, "abc123", "wrong_topic")

    def test_done_returns_none_new_format(self):
        from telegram_bot.callback_data import FeedbackCB
        from telegram_bot.feedback import parse_feedback_callback

        packed = FeedbackCB(action="done", trace_id="").pack()
        assert parse_feedback_callback(packed) is None

    def test_keyboard_like_button_parseable(self):
        from telegram_bot.feedback import build_feedback_keyboard, parse_feedback_callback

        kb = build_feedback_keyboard("trace_abc")
        like_btn = kb.inline_keyboard[0][0]
        result = parse_feedback_callback(like_btn.callback_data or "")
        assert result is not None
        value, trace_id, reason = result
        assert value == 1.0
        assert trace_id == "trace_abc"
        assert reason is None

    def test_keyboard_dislike_button_parseable(self):
        from telegram_bot.feedback import build_feedback_keyboard, parse_feedback_callback

        kb = build_feedback_keyboard("trace_abc")
        dislike_btn = kb.inline_keyboard[0][1]
        result = parse_feedback_callback(dislike_btn.callback_data or "")
        assert result is not None
        value, trace_id, reason = result
        assert value == 0.0
        assert trace_id == "trace_abc"
        assert reason is None

    def test_reason_keyboard_buttons_parseable(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard, parse_feedback_callback

        kb = build_dislike_reason_keyboard("trace_xyz")
        for row in kb.inline_keyboard:
            for btn in row:
                result = parse_feedback_callback(btn.callback_data or "")
                assert result is not None
                value, trace_id, reason = result
                assert value == 0.0
                assert trace_id == "trace_xyz"
                assert reason is not None
