from core.config import Settings


def test_llm_planner_is_disabled_by_default_and_can_be_enabled() -> None:
    default_settings = Settings(postgres_password="test-password")
    enabled_settings = Settings(postgres_password="test-password", llm_planner_enabled=True)

    assert default_settings.llm_planner_enabled is False
    assert enabled_settings.llm_planner_enabled is True
