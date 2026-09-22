import sys

filename = '/home/codeser_server/Data/projects/roombeacon/source/roombeacon-system/crawler/src/roombeacon_crawler/pipeline/crawl_runner.py'
with open(filename, 'r') as f:
    content = f.read()

# Add exit_transition = None before while
content = content.replace(
    '        while state.current_page <= state.effective_end_page:',
    '        exit_transition = None\n        while state.current_page <= state.effective_end_page:'
)

# Add exit_transition = acquisition_decision.transition before break
content = content.replace(
    '                break\n            page_records_count = len(cards)',
    '                exit_transition = acquisition_decision.transition\n                break\n            page_records_count = len(cards)'
)

# Add exit_transition = frontier_decision.transition before break
content = content.replace(
    '            if frontier_decision.should_stop:\n                break\n        frontier_started = time.perf_counter()',
    '            if frontier_decision.should_stop:\n                exit_transition = frontier_decision.transition\n                break\n        frontier_started = time.perf_counter()'
)

# Fix the end block
old_end = """        from roombeacon_crawler.application.crawl.frontier_decision import FrontierTransition
        if state.current_page > state.effective_end_page:
            exit_transition = FrontierTransition.PAGE_RANGE_EXHAUSTED
        else:
            exit_transition = frontier_decision.transition"""

new_end = """        if exit_transition is None:
            from roombeacon_crawler.application.crawl.frontier_decision import FrontierTransition
            exit_transition = FrontierTransition.PAGE_RANGE_EXHAUSTED"""

content = content.replace(old_end, new_end)

with open(filename, 'w') as f:
    f.write(content)
print("Patched.")
