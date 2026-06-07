/* File 2: price accounts using the rate table (reads WORK tables from file 1). */
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
