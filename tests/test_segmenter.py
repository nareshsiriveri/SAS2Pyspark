from sas2spark.parse import segment, split_statements, strip_comments
from sas2spark.models import StepKind


def test_strip_block_comments_respects_strings():
    src = "data x; y = '/* not a comment */'; /* real comment */ z = 1; run;"
    cleaned = strip_comments(src)
    assert "/* not a comment */" in cleaned  # inside a string, preserved
    assert "real comment" not in cleaned     # actual comment removed


def test_split_drops_star_comments():
    stmts = split_statements("* this is a comment; data x; set y; run;")
    assert stmts[0].lower().startswith("data")


def test_segment_basic_data_and_proc():
    src = """
    data work.a; set raw.a; run;
    proc sql; create table work.b as select * from work.a; quit;
    """
    steps = segment(src)
    assert len(steps) == 2
    assert steps[0].kind is StepKind.DATA
    assert steps[1].kind is StepKind.PROC
    assert steps[1].proc_name == "sql"


def test_implicit_step_boundary_without_run():
    # No run; before the next data step — should still split.
    src = "data a; set raw.a; data b; set raw.b; run;"
    steps = segment(src)
    assert len(steps) == 2
    assert {s.outputs[0].name for s in steps} == {"a", "b"}


def test_quoted_semicolon_not_a_boundary():
    src = "data a; msg = 'hello; world'; set raw.a; run;"
    steps = segment(src)
    assert len(steps) == 1
    assert any("hello; world" in st for st in steps[0].statements)
