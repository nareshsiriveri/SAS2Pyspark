"""Dual-source macro provenance: separate data-derived literals from structural ones."""
from sas2spark.flatten import flatten
from sas2spark.flatten.macro_context import (
    attach_macro_context,
    derived_substitutions,
    extract_macro_defs,
    harvest_log,
)
from sas2spark.flatten.macro_context import _let_vars  # noqa: PLC2701 - testing internals
from sas2spark.llm.prompts import translation_prompt
from sas2spark.parse import segment

# --- A linear-scoring macro: coefficients are data-derived macro variables. ---
SCORE_SAS = """\
%macro score(snapshot=, score_name=, n_var=, var_list=);
   data &snapshot.;
      set &snapshot.;
      &score_name. = 0
      %do i = 1 %to &n_var.;
         %let var_name = %scan(&var_list., &i.);
         + &&&var_name..*&var_name.
      %end; ;
   run;
%mend score;
%score(snapshot=x_oo_res, score_name=score, n_var=5, var_list=INTERCEPT BIGCITY SEGMENT YEARS CCI);
"""

SCORE_LOG = """\
MLOGIC(SCORE):  Parameter SNAPSHOT has value x_oo_res
MLOGIC(SCORE):  Parameter SCORE_NAME has value score
MLOGIC(SCORE):  Parameter N_VAR has value 5
MLOGIC(SCORE):  Parameter VAR_LIST has value INTERCEPT BIGCITY SEGMENT YEARS CCI
MPRINT(SCORE):   data x_oo_res;
MPRINT(SCORE):   set x_oo_res;
MLOGIC(SCORE):  %DO loop beginning; index variable I; start value is 1; stop value is 5.
SYMBOLGEN:  Macro variable I resolves to 1
SYMBOLGEN:  Macro variable VAR_NAME resolves to INTERCEPT
SYMBOLGEN:  Macro variable INTERCEPT resolves to -0.00637
SYMBOLGEN:  Macro variable VAR_NAME resolves to BIGCITY
SYMBOLGEN:  Macro variable BIGCITY resolves to 0
SYMBOLGEN:  Macro variable VAR_NAME resolves to SEGMENT
SYMBOLGEN:  Macro variable SEGMENT resolves to 0
SYMBOLGEN:  Macro variable VAR_NAME resolves to YEARS
SYMBOLGEN:  Macro variable YEARS resolves to -0.1062
SYMBOLGEN:  Macro variable VAR_NAME resolves to CCI
SYMBOLGEN:  Macro variable CCI resolves to 0.2762
MPRINT(SCORE):   score=0 + -0.00637*INTERCEPT + 0*BIGCITY + 0*SEGMENT + -0.1062*YEARS + 0.2762*CCI;
MPRINT(SCORE):   run;
"""


def test_harvest_log_classifies_macro_vars():
    info = harvest_log(SCORE_LOG)
    assert info.loop_vars == {"I"}
    assert {"SNAPSHOT", "SCORE_NAME", "N_VAR", "VAR_LIST"} <= info.param_vars
    assert info.symbol_values["INTERCEPT"] == "-0.00637"
    assert "SCORE" in info.macro_emitted


def test_derived_substitutions_keeps_only_coefficients():
    info = harvest_log(SCORE_LOG)
    derived = derived_substitutions(info, _let_vars(SCORE_SAS))
    # The five coefficients are data-derived...
    assert set(derived) == {"INTERCEPT", "BIGCITY", "SEGMENT", "YEARS", "CCI"}
    # ...and structural vars (loop index, params, %let'd VAR_NAME) are excluded.
    assert "I" not in derived
    assert "N_VAR" not in derived  # numeric, but a macro parameter
    assert "VAR_NAME" not in derived  # %let-assigned


def test_attach_marks_coefficients_on_the_scoring_step():
    steps = segment(flatten(SCORE_LOG))
    attach_macro_context(steps, SCORE_SAS, SCORE_LOG)
    data_steps = [s for s in steps if s.macro_context is not None]
    assert len(data_steps) == 1
    ctx = data_steps[0].macro_context
    assert ctx.macro_names == ["SCORE"]
    assert "%macro score" in ctx.original_source
    got = {(s.macro_var, s.value) for s in ctx.substitutions}
    assert got == {
        ("INTERCEPT", "-0.00637"),
        ("BIGCITY", "0"),
        ("SEGMENT", "0"),
        ("YEARS", "-0.1062"),
        ("CCI", "0.2762"),
    }


def test_prompt_includes_macro_context():
    steps = segment(flatten(SCORE_LOG))
    attach_macro_context(steps, SCORE_SAS, SCORE_LOG)
    step = next(s for s in steps if s.macro_context is not None)
    prompt = translation_prompt(step)
    assert "MACRO EXPANSION" in prompt
    assert "%macro score" in prompt
    assert "INTERCEPT = -0.00637" in prompt
    assert "externalize" in prompt.lower()


def test_extract_macro_defs():
    defs = extract_macro_defs(SCORE_SAS)
    assert "SCORE" in defs
    assert defs["SCORE"].lower().startswith("%macro score")
    assert "%mend" in defs["SCORE"].lower()


# --- A purely structural macro (region x year) must NOT be flagged. ---
STRUCT_SAS = """\
%macro summarize(regions=, years=);
   %do i = 1 %to 2;
      %let region = %scan(&regions, &i);
      %do y = 1 %to 2;
         %let year = %scan(&years, &y);
         data work.acct_&region._&year;
            set raw.transactions;
            where region = "&region" and year = &year;
         run;
      %end;
   %end;
%mend summarize;
%summarize(regions=US EU, years=2022 2023);
"""

STRUCT_LOG = """\
MLOGIC(SUMMARIZE):  Parameter REGIONS has value US EU
MLOGIC(SUMMARIZE):  Parameter YEARS has value 2022 2023
MLOGIC(SUMMARIZE):  %DO loop beginning; index variable I; start value is 1; stop value is 2.
SYMBOLGEN:  Macro variable I resolves to 1
SYMBOLGEN:  Macro variable REGION resolves to US
MLOGIC(SUMMARIZE):  %DO loop beginning; index variable Y; start value is 1; stop value is 2.
SYMBOLGEN:  Macro variable Y resolves to 1
SYMBOLGEN:  Macro variable YEAR resolves to 2022
MPRINT(SUMMARIZE):   data work.acct_US_2022;
MPRINT(SUMMARIZE):   set raw.transactions;
MPRINT(SUMMARIZE):   where region = "US" and year = 2022;
MPRINT(SUMMARIZE):   run;
"""


def test_structural_macro_is_not_flagged():
    # YEAR resolves to a number (2022) but is %let-assigned from a %scan of a
    # parameter list — structural, not data-derived. No context should attach.
    steps = segment(flatten(STRUCT_LOG))
    attach_macro_context(steps, STRUCT_SAS, STRUCT_LOG)
    assert all(s.macro_context is None for s in steps)
