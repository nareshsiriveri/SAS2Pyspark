/* Example SAS program exercising DATA steps, MERGE, BY/RETAIN, and PROC SQL. */

data work.accounts;
    set raw.accounts;
    where balance > 0;
    region = upcase(region);
run;

data work.rates;
    set raw.rates;
run;

/* Join accounts to their region rate, then compute interest. */
proc sql;
    create table work.priced as
    select a.account_id,
           a.region,
           a.balance,
           r.rate,
           a.balance * r.rate as interest
    from work.accounts as a
    left join work.rates as r
    on a.region = r.region;
quit;

/* Running total of interest within region, ordered by account_id. */
proc sort data=work.priced;
    by region account_id;
run;

data work.cumulative;
    set work.priced;
    by region;
    retain running_interest;
    if first.region then running_interest = 0;
    running_interest + interest;
run;

/* Region-level summary. */
proc sql;
    create table work.region_summary as
    select region,
           count(*) as n_accounts,
           sum(balance) as total_balance,
           sum(interest) as total_interest
    from work.cumulative
    group by region;
quit;
