from sas2spark.flatten import flatten, flatten_log, looks_like_log

LOG = """\
1    %macro build(lib);
MLOGIC(BUILD):  Beginning execution.
SYMBOLGEN:  Macro variable LIB resolves to work
MPRINT(BUILD):   data work.a;
MPRINT(BUILD):   set raw.a;
MPRINT(BUILD):   run;
NOTE: The data set WORK.A has 10 observations.
MPRINT(BUILD):   proc print data=work.a;
MPRINT(BUILD):   run;
"""


def test_looks_like_log():
    assert looks_like_log(LOG)
    assert not looks_like_log("data x; set y; run;")


def test_flatten_log_harvests_mprint():
    out = flatten_log(LOG)
    assert "data work.a;" in out
    assert "set raw.a;" in out
    assert "proc print data=work.a;" in out
    # Noise lines must be gone.
    assert "MLOGIC" not in out
    assert "NOTE:" not in out
    assert "%macro" not in out


def test_flatten_passes_through_plain_sas():
    src = "data x; set y; run;"
    assert flatten(src) == src
