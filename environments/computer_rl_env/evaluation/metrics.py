from typing import Any, Dict, List, Optional


def compute_success_rate(results: List[Dict[str, Any]]) -> float:
    """
    Compute the overall success rate from a list of evaluation results.

    Args:
        results: List of result dictionaries, each containing a 'success' boolean.

    Returns:
        float: Success rate between 0.0 and 1.0.
    """
    if not results:
        return 0.0

    success_count = sum(1 for r in results if r.get("success", False))
    return success_count / len(results)


def compute_efficiency_score(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Compute efficiency metrics (average steps, time) for successful episodes.

    Args:
        results: List of result dictionaries containing 'step_count' and 'elapsed_time'.

    Returns:
        Dict containing 'avg_steps' and 'avg_time'.
    """
    successful_episodes = [r for r in results if r.get("success", False)]

    if not successful_episodes:
        return {"avg_steps": 0.0, "avg_time": 0.0}

    total_steps = sum(r.get("step_count", 0) for r in successful_episodes)

    # Check if elapsed_time is available, otherwise default to 0
    total_time = sum(r.get("elapsed_time", 0.0) for r in successful_episodes)

    count = len(successful_episodes)

    return {"avg_steps": total_steps / count, "avg_time": total_time / count}


def compute_category_breakdown(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Break down success rate by task category.

    Args:
        results: List of result dictionaries containing 'task_category' or metadata with category.

    Returns:
        Dict mapping categories to their stats (success_rate, count).
    """
    categories = {}

    for r in results:
        # Try to find category in different places
        category = r.get("category", "unknown")
        if category == "unknown" and "task_metadata" in r:
            category = r["task_metadata"].get("category", "unknown")

        if category not in categories:
            categories[category] = {"total": 0, "success": 0}

        categories[category]["total"] += 1
        if r.get("success", False):
            categories[category]["success"] += 1

    # Compute rates
    breakdown = {}
    for cat, stats in categories.items():
        total = stats["total"]
        if total > 0:
            rate = stats["success"] / total
        else:
            rate = 0.0

        breakdown[cat] = {
            "success_rate": rate,
            "total_episodes": total,
            "success_count": stats["success"],
        }

    return breakdown


def generate_report(results: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """
    Generate a simple text report of the evaluation results.

    Args:
        results: aggregated results dictionary
        output_path: Optional path to save the report to.

    Returns:
        str: The report text.
    """
    import json

    report_lines = []
    report_lines.append("=== Evaluation Report ===")
    report_lines.append(f"Total Episodes: {results.get('total_episodes', 0)}")
    report_lines.append(f"Success Rate: {results.get('success_rate', 0.0):.2%}")

    efficiency = results.get("efficiency", {})
    report_lines.append(f"Average Steps (Successes): {efficiency.get('avg_steps', 0.0):.1f}")
    report_lines.append(f"Average Time (Successes): {efficiency.get('avg_time', 0.0):.2f}s")

    report_lines.append("\n=== Category Breakdown ===")
    breakdown = results.get("category_breakdown", {})
    for cat, stats in breakdown.items():
        report_lines.append(
            f"{cat}: {stats['success_rate']:.2%} ({stats['success_count']}/{stats['total_episodes']})"
        )

    report_text = "\n".join(report_lines)

    if output_path:
        # If output path ends in .json, save full results as JSON
        if output_path.endswith(".json"):
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
        else:
            # Otherwise save text report
            with open(output_path, "w") as f:
                f.write(report_text)

    return report_text
