/* File 1: load & clean source tables into WORK. */
data work.accounts;
    set raw.accounts;
    where balance > 0;
    region = upcase(region);
run;

data work.rates;
    set raw.rates;
run;
