/* Linear-scoring macro: SCORE = sum over a variable list of (coef_v * column_v).
   The coefficients live in macro variables (one per variable) that were pushed in
   from a parameter-estimates table via CALL SYMPUT elsewhere. &&&VAR_NAME. does a
   double resolution: &VAR_NAME -> the column name, then &<that name> -> its coef.

   Run with:  options mprint mlogic symbolgen;  to harvest score_macro.log.
   The flattener consumes the log; this .sas is the parametric source the
   dual-source macro translator pairs with it (sibling .sas next to the .log). */

%macro score(snapshot=, score_name=, n_var=, var_list=);
   data &snapshot.;
      set &snapshot.;
      &score_name. = 0
      %do i = 1 %to &n_var.;
         %let var_name = %scan(&var_list., &i.);
         + &&&var_name..*&var_name.
      %end;
      ;
   run;
%mend score;

%score(snapshot=x_oo_res, score_name=score, n_var=5,
       var_list=INTERCEPT BIGCITY SEGMENT YEARS CCI);
