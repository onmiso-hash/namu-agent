"""글자 파일 판정 시험.

확장자만 믿으면 `.md` 이름을 단 바이너리가 왔을 때 깨진 글자를 저장하게 되고,
UTF-8 해독만 믿으면 짧은 바이너리가 우연히 해독에 성공해 글자로 잘못 분류된다.
이 파일은 **셋(확장자·크기·해독)이 전부 필요하다**는 것을 못박는다.
"""
import attach_text


def test_a_plain_text_file_comes_back_as_text():
    assert attach_text.as_text("attach_file/메모.md", "한 줄".encode("utf-8")) == "한 줄"


def test_a_binary_is_not_text_even_with_a_text_extension():
    assert attach_text.as_text("attach_file/속임수.md", b"\xff\xfe\x00\x01") is None


def test_valid_utf8_is_not_text_without_a_text_extension():
    # `.pptx` 안이 우연히 해독되더라도 글자로 다루면 안 된다.
    assert attach_text.as_text("attach_file/발표.pptx", b"hello") is None


def test_text_over_the_limit_is_withheld():
    big = b"a" * (attach_text.MAX_INLINE_TEXT_BYTES + 1)

    assert attach_text.as_text("attach_file/큰글.md", big) is None


def test_text_exactly_at_the_limit_still_passes():
    edge = b"a" * attach_text.MAX_INLINE_TEXT_BYTES

    assert attach_text.as_text("attach_file/딱맞음.md", edge) is not None


def test_a_dotfile_name_counts_as_its_own_extension():
    assert attach_text.has_text_extension(".gitignore") is True


def test_a_name_with_no_extension_is_not_text():
    assert attach_text.has_text_extension("attach_file/README") is False


def test_the_extension_check_ignores_letter_case():
    assert attach_text.has_text_extension("attach_file/NOTE.MD") is True
