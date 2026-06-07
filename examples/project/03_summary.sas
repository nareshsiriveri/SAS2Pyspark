/* File 3: region-level summary (reads work.priced from file 2). */
proc sql;
    create table work.region_summary as
    select region,
           count(*) as n_accounts,
           sum(balance) as total_balance,
           sum(interest) as total_interest
    from work.priced
    group by region;
quit;
