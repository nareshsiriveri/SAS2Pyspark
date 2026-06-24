/* ==========================================================================
   Complex macro pipeline — per-(segment, month) customer risk scoring.

   Exercises everything the translator now understands:
     * nested %do loops          -> STRUCTURAL macro vars (segment, month, K, V,
                                     setlist): the MPRINT expansion is exactly the
                                     right code, so it is translated as-is.
     * a linear risk score       -> DATA-DERIVED macro vars (the coefficients):
                                     they come from a fitted model via CALL SYMPUT,
                                     not %let/params/loop, so the dual-source
                                     translator externalizes them instead of
                                     hardcoding the run's literals.
     * a PROC SQL GROUP BY       -> REMERGE: a non-grouped column sits next to
                                     aggregates, so SAS keeps every detail row and
                                     remerges the group total — a Spark *window*,
                                     not groupBy.

   Run once with:  options mprint mlogic symbolgen;   -> risk_pipeline.log
   Keep this .sas next to the .log so dual-source macro translation kicks in.
   ========================================================================== */

options mprint mlogic symbolgen;

/* Coefficients of a fitted model, pushed into macro variables. Because they are
   set by CALL SYMPUT (data-derived) rather than %let/parameters/loop indices,
   the framework flags them as parameters to externalize. */
data _null_;
   set model.params;                 /* columns: varname, estimate */
   call symput(strip(varname), strip(put(estimate, best16.)));
run;

%let var_list = INTERCEPT TENURE BALANCE NUMTX CCI;
%let n_var    = 5;

%macro score_book(segs=, months=);
   %local i j s m k v setlist;
   %let setlist = ;

   %do i = 1 %to %sysfunc(countw(&segs));
      %let s = %scan(&segs, &i);

      %do j = 1 %to %sysfunc(countw(&months));
         %let m = %scan(&months, &j);

         /* 1. slice this segment+month and derive a feature */
         data work.cust_&s._&m;
            set raw.customers;
            where segment = "&s" and month = &m;
            tenure_yrs = tenure / 12;
         run;

         /* 2. score: risk = sum_k  coef[v_k] * column v_k   (&&&v -> coefficient) */
         data work.scored_&s._&m;
            set work.cust_&s._&m;
            risk_score = 0
               %do k = 1 %to &n_var;
                  %let v = %scan(&var_list, &k);
                  + &&&v..*&v.
               %end; ;
            length segment $8;
            segment = "&s";
            month   = &m;
         run;

         %let setlist = &setlist work.scored_&s._&m;
      %end;
   %end;

   /* 3. stack every scored slice */
   data work.scored_all;
      set &setlist;
   run;

   /* 4. each customer's share of its (segment, month) total risk — REMERGE:
         all detail rows are kept and the group total is merged back on. */
   proc sql;
      create table work.risk_share as
      select segment, month, custid, risk_score,
             risk_score / sum(risk_score) as risk_pct,
             mean(risk_score)             as seg_avg_score
      from work.scored_all
      group by segment, month;
   quit;
%mend score_book;

%score_book(segs=RETAIL SME, months=1 2);
