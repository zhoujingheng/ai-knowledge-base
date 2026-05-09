"""Quick test of planner integration"""
import os
os.environ["PLANNER_TARGET_COUNT"] = "5"

from workflows.planner import planner_node
from workflows.state import KBState

# Test planner_node
state: KBState = {
    "plan": {},
    "sources": [],
    "analyses": [],
    "articles": [],
    "review_feedback": "",
    "review_passed": False,
    "iteration": 0,
    "needs_human_review": False,
    "cost_tracker": {}
}

result = planner_node(state)
print("\n=== Planner Output ===")
print(f"Strategy: {result['plan']['strategy']}")
print(f"Per source limit: {result['plan']['per_source_limit']}")
print(f"Relevance threshold: {result['plan']['relevance_threshold']}")
print(f"Max iterations: {result['plan']['max_iterations']}")
print(f"Rationale: {result['plan']['rationale']}")

# Test with different targets
print("\n=== Testing Different Targets ===")
for target in [5, 10, 15, 20, 30]:
    os.environ["PLANNER_TARGET_COUNT"] = str(target)
    result = planner_node({})
    plan = result['plan']
    print(f"Target {target:2d} → {plan['strategy']:8s} (limit={plan['per_source_limit']:2d}, threshold={plan['relevance_threshold']:.1f}, max_iter={plan['max_iterations']})")
