def pytest_itemcollected(item):
    """Show the first line of each test's docstring instead of its function name."""
    doc = item.function.__doc__
    if doc:
        item._nodeid = doc.strip().splitlines()[0]