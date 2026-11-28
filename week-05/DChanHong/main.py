import argparse

from agents import MaxTurnsExceeded, Runner

from ipo_agent.agents.subscription import subscription_agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", help="에이전트에 전달할 요청입니다.")
    args = parser.parse_args()

    try:
        result = Runner.run_sync(subscription_agent, args.request, max_turns=12)
    except MaxTurnsExceeded:
        print("목표 미달성 | 12턴 한도에 도달했습니다.")
        return

    for item in result.new_items:
        if item.type == "tool_call_item":
            print(f"[도구 호출] {item.raw_item.name} {item.raw_item.arguments}")

    print(result.final_output)


if __name__ == "__main__":
    main()
