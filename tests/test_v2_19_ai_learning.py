from app.learning.ai_learning_builder import AILearningBuilder


def test_ai_useful_call_rewarded():
    item = AILearningBuilder().build({"model_name": "local", "task_type": "review", "useful": True, "accuracy_score": 0.8})
    assert item.learning_signal == "reward_ai"


def test_ai_bad_call_penalized():
    item = AILearningBuilder().build({"model_name": "local", "task_type": "review", "accuracy_score": 0.2})
    assert item.learning_signal == "penalize_ai"
