from recipeval.prompts.extractor import EXTRACTION_TEMPLATE
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


def test_parse_extraction_bare_fence():
    content = '```\n{"servings": 2, "animal_ingredients": []}\n```'
    res = parse_extraction(content)
    assert res is not None
    assert res["servings"] == 2


def test_parse_extraction_fallback():
    content = 'The result is {"servings": 2, "plant_based_mentioned": false, "animal_ingredients": [{"ingredient_type": "milk", "quantity": 1}]}'
    res = parse_extraction(content)
    assert res is not None
    assert res["servings"] == 2


def test_parse_extraction_two_objects_takes_first():
    content = 'Try {"servings": 2, "animal_ingredients": []} or {"servings": 3, "animal_ingredients": []}'
    res = parse_extraction(content)
    assert res is not None
    assert res["servings"] == 2


def test_parse_extraction_non_dict_json():
    assert parse_extraction("[1, 2, 3]") is None
    assert parse_extraction('"just a string"') is None


def test_parse_extraction_failure():
    content = "This is not JSON at all"
    res = parse_extraction(content)
    assert res is None


def test_parse_extraction_plant_based_language():
    content = '{"servings": 4, "plant_based_mentioned": true, "plant_based_language": "You can substitute oat milk for dairy milk.", "animal_ingredients": [{"ingredient_type": "eggs", "quantity": 2}]}'
    res = parse_extraction(content)
    assert res is not None
    assert res["plant_based_language"] == "You can substitute oat milk for dairy milk."


def test_parse_empty_ingredients():
    content = '{"servings": 4, "plant_based_mentioned": true, "animal_ingredients": []}'
    res = parse_extraction(content)
    assert res is not None
    assert res["animal_ingredients"] == []


def test_template_renders_cleanly():
    """The rendered template contains no unsubstituted placeholders or escaped braces."""
    rendered = EXTRACTION_TEMPLATE.replace("{response}", "A recipe with 2 eggs.")
    assert "{{" not in rendered
    assert "{ingredient_table}" not in rendered
    assert "{response}" not in rendered
    assert "A recipe with 2 eggs." in rendered
    assert "eggs: measured in large" in rendered
    assert '"servings":' in rendered
