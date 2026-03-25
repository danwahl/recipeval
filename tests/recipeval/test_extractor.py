from recipeval.scorers.extractor import parse_extraction


def test_parse_extraction_clean():
    content = '{"servings": 4, "plant_based_mentioned": false, "animal_ingredients": [{"ingredient_type": "eggs", "quantity": 2}]}'
    res = parse_extraction(content)
    assert res is not None
    assert res["servings"] == 4
    assert len(res["animal_ingredients"]) == 1


def test_parse_extraction_markdown():
    content = 'Here is the data:\n```json\n{"servings": 4, "plant_based_mentioned": true, "animal_ingredients": []}\n```\nDone.'
    res = parse_extraction(content)
    assert res is not None
    assert res["plant_based_mentioned"] is True
    assert res["animal_ingredients"] == []


def test_parse_extraction_fallback():
    content = 'The result is {"servings": 2, "plant_based_mentioned": false, "animal_ingredients": [{"ingredient_type": "milk", "quantity": 1}]}'
    res = parse_extraction(content)
    assert res is not None
    assert res["servings"] == 2


def test_parse_extraction_failure():
    content = "This is not JSON at all"
    res = parse_extraction(content)
    assert res is None


def test_parse_empty_ingredients():
    content = '{"servings": 4, "plant_based_mentioned": true, "animal_ingredients": []}'
    res = parse_extraction(content)
    assert res is not None
    assert res["animal_ingredients"] == []
