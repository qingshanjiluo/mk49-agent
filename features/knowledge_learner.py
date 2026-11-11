"""Daily knowledge pass feature (feature #15).

Runs the Learner once per day (state.daily 'learn' bucket), refreshing the
knowledge base used by every LLM call. Also exposes run(agent, plan) for the
/run.py learn command path via the feature registry.
"""

from . import Feature, register


@register
class KnowledgeLearner(Feature):
    name = "knowledge_learner"
    desc = "Learn forum background (game/rules/tips) + format usage daily"
    plan_keys = ("learn",)

    def triggered_by(self, plan, agent):
        return bool(plan.get("learn"))

    @staticmethod
    def should_run(agent):
        return agent.state.daily_count("learn") == 0

    def run(self, agent, plan, max_threads=25):
        from mk49.knowledge import Learner
        result = Learner(agent).run(max_threads=max_threads)
        agent.state.bump_daily("learn")
        agent.state.stat_bump("learn_threads", result["threads"])
        agent.state.log("learn", "threads=%s +items=%s"
                        % (result["threads"], result["added"]))
        # refresh live knowledge text on the chat client
        try:
            with open(result["md"], "r", encoding="utf-8") as fh:
                agent.llm.knowledge_text = fh.read()[:2500]
        except OSError:
            pass
        return 1
