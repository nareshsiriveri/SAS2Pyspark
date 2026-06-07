from sas2spark.parse import segment
from sas2spark.models import DatasetRef


def _step(src):
    return segment(src)[0]


def test_data_step_set_and_output():
    s = _step("data work.out; set raw.in; run;")
    assert DatasetRef("work", "out") in s.outputs
    assert DatasetRef("raw", "in") in s.inputs


def test_data_step_merge_multiple_inputs():
    s = _step("data work.m; merge a b raw.c; by id; run;")
    keys = {r.key for r in s.inputs}
    assert {"work.a", "work.b", "raw.c"} <= keys


def test_set_option_not_treated_as_dataset():
    s = _step("data work.o; set raw.in end=eof; run;")
    keys = {r.key for r in s.inputs}
    assert "work.eof" not in keys
    assert "raw.in" in keys


def test_dataset_options_stripped():
    s = _step("data work.o; set raw.in(where=(x>0) keep=a b); run;")
    assert DatasetRef("raw", "in") in s.inputs


def test_proc_sql_create_from_join():
    s = _step(
        "proc sql; create table work.j as "
        "select * from work.a as x left join work.b as y on x.id=y.id; quit;"
    )
    assert DatasetRef("work", "j") in s.outputs
    keys = {r.key for r in s.inputs}
    assert {"work.a", "work.b"} <= keys


def test_proc_sort_in_place():
    s = _step("proc sort data=work.t; by id; run;")
    assert DatasetRef("work", "t") in s.outputs
    assert DatasetRef("work", "t") in s.inputs


def test_proc_generic_data_out_options():
    s = _step("proc means data=work.t out=work.summary; var x; run;")
    assert DatasetRef("work", "t") in s.inputs
    assert DatasetRef("work", "summary") in s.outputs
