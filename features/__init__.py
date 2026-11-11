"""Feature base class.

A feature is enabled/disabled, declares which plan keys trigger it, and does
its work inside run(agent, plan), returning the number of actions performed.
"""

FEATURES = {}


def register(cls):
    FEATURES[cls.name] = cls()
    return cls


class Feature:
    name = "base"
    desc = ""
    enabled = True
    plan_keys = ()

    def triggered_by(self, plan, agent):
        return any(plan.get(k) for k in self.plan_keys)

    def run(self, agent, plan):
        raise NotImplementedError


def load_all():
    """Import every feature module so @register fires."""
    from . import (  # noqa: F401
        smart_comment, image_post, url_card, welcome_newcomer, daily_digest,
        poll_rider, like_curator, mention_watch, command_center,
        content_safety, thread_summarizer, hot_topic_tracker,
        series_builder, emoji_enhancer,
    )
    return FEATURES
