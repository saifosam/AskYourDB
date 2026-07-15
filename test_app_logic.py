import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("app_module", Path(__file__).with_name("app.py"))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)


def test_irrelevant_prompt_is_denied():
    result = app_module.check_relevance("what is the weather tomorrow")
    assert result["relevant"] is False


def test_nonsense_prompt_is_denied():
    result = app_module.check_relevance("wakadodo")
    assert result["relevant"] is False
    assert "database" in result["reason"].lower()


def test_money_query_is_denied_for_missing_data():
    result = app_module.check_data_availability("who made the most money")
    assert result["available"] is False


def test_people_name_prefix_query_is_allowed():
    result = app_module.check_data_availability("show me all the people whose names start with a c")
    assert result["available"] is True


def test_people_country_query_is_allowed():
    result = app_module.check_data_availability("show me all the people in Germany")
    assert result["available"] is True


def test_followup_rewrite_country():
    history = [{"q": "give me all the people who are in germany", "sql": "SELECT 1"}]
    rewritten = app_module.rewrite_followup_question("what about france", history)
    assert "france" in rewritten.lower()
    assert "people" in rewritten.lower()


def test_known_customer_question_is_allowed():
    result = app_module.check_data_availability("show me customers from Germany")
    assert result["available"] is True
