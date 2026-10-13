from app.services.normalizer import contains_marker, dedupe, group_key, normalize_phrase, prepare


def test_normalize_spaces_case_and_yo() -> None:
    assert normalize_phrase("  Счёт   НА  Оплату ") == "счет на оплату"


def test_normalize_removes_wordstat_operators_and_punctuation() -> None:
    assert normalize_phrase('"!конвертер +pdf [в word]"') == "конвертер pdf в word"
    assert normalize_phrase("купить crm -бесплатно") == "купить crm"


def test_normalize_keeps_meaningful_symbols() -> None:
    assert normalize_phrase("Курсы C++ и C#") == "курсы c++ и c#"
    assert normalize_phrase("pdf-файл, онлайн!") == "pdf-файл онлайн"


def test_normalize_empty() -> None:
    assert normalize_phrase(" !!! ") == ""
    assert prepare("   ") is None


def test_dedupe_keeps_first_original() -> None:
    items = dedupe(["Конвертер PDF", "конвертер  pdf", "конвертер pdf!", "объединить pdf"])
    assert [i.normalized for i in items] == ["конвертер pdf", "объединить pdf"]
    assert items[0].original == "Конвертер PDF"


def test_group_key_merges_word_forms() -> None:
    assert group_key("конвертер pdf") == group_key("конвертеры pdf")
    assert group_key("генератор счетов") == group_key("генератор счета")


def test_group_key_keeps_different_intents_apart() -> None:
    # Одинаковые слова, противоположное намерение — не объединяем.
    assert group_key("из pdf в word") != group_key("из word в pdf")
    assert group_key("купить crm") != group_key("crm бесплатно")


def test_contains_marker_word_start() -> None:
    assert contains_marker("выставить счета онлайн", "счет")
    assert not contains_marker("пересчет цен", "счет")
    assert contains_marker("учет для ип быстро", "ип ")
    assert not contains_marker("типография", "ип ")
    assert contains_marker("crm для малого бизнеса", "малого бизнеса")
