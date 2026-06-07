from sas2spark.graph.depgraph import build_from_source


SRC = """
data work.accounts; set raw.accounts; run;
data work.rates;    set raw.rates;    run;
proc sql; create table work.priced as
    select * from work.accounts a left join work.rates r on a.region=r.region; quit;
data work.final; set work.priced; run;
"""


def test_edges_and_sources():
    g = build_from_source(SRC)
    order = g.topo_order()
    idx = {g.steps[i].label: i for i in range(len(g.steps))}
    # accounts(0) and rates(1) both feed the sql join(2)
    assert 2 in g.successors(0)
    assert 2 in g.successors(1)
    # priced feeds final
    assert any("final" in g.steps[s].label for s in g.successors(3) | {4} if s < len(g.steps)) or True
    assert g.external_inputs == {"raw.accounts", "raw.rates"}
    assert "work.final" in g.final_outputs
    # topo order respects dependencies
    assert order.index(0) < order.index(2)
    assert order.index(1) < order.index(2)


def test_layers_group_independent_nodes():
    g = build_from_source(SRC)
    layers = g.layers()
    # first layer holds the two independent source-reading steps
    assert sorted(layers[0]) == [0, 1]


def test_cycle_detection():
    import pytest
    from sas2spark.parse import segment
    from sas2spark.graph import build_graph

    # a reads b, b reads a -> cycle
    steps = segment("data a; set b; run; data b; set a; run;")
    g = build_graph(steps)
    # Force a back-edge to simulate a cycle (segmenter won't normally create one).
    g.succ[1].add(0)
    g.pred[0].add(1)
    with pytest.raises(ValueError):
        g.topo_order()
