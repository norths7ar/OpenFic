from app.agent_runtime.context.errors import ContextBuildError


def test_context_build_error_format():
    err = ContextBuildError("environment", "chapter not found")
    assert err.part == "environment"
    assert err.reason == "chapter not found"
    assert "[context:environment]" in str(err)
