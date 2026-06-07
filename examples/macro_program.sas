/* Complex macro with nested %do loops over regions x years.
   Run with:  options mprint mlogic symbolgen;  to harvest the expanded log
   (see macro_program.log) — the flattener consumes that log, not this source. */

%macro summarize(regions=, years=);
   %local i r y region year setlist;
   %let setlist = ;

   %do i = 1 %to %sysfunc(countw(&regions));
      %let region = %scan(&regions, &i);

      %do y = 1 %to %sysfunc(countw(&years));
         %let year = %scan(&years, &y);

         /* per-(region, year) slice with FX conversion */
         data work.acct_&region._&year;
            set raw.transactions;
            where region = "&region" and year = &year;
            amount_usd = amount * fx_rate;
         run;

         /* aggregate the slice */
         proc means data=work.acct_&region._&year noprint;
            var amount_usd;
            output out=work.sum_&region._&year (drop=_type_ _freq_) sum=total_usd;
         run;

         /* tag the aggregate with its region/year */
         data work.sum_&region._&year;
            set work.sum_&region._&year;
            length region $2;
            region = "&region";
            year   = &year;
         run;

         %let setlist = &setlist work.sum_&region._&year;
      %end;
   %end;

   /* stack every per-slice summary into one table */
   data work.all_summaries;
      set &setlist;
   run;
%mend summarize;

%summarize(regions=US EU, years=2022 2023);
