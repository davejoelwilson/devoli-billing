# PROCESS

1. Go to Devoli and download the e-bill fie
2. Take the file into access and get the output
3. Open the output in Excel, highlight yellow just the calling calls, e.g hust the Australian calls, local calls, mobile calls, national calls. 
4. Go through and add the rates manually
5. Calulcate the seconds/minutes manually, the charge, and the sum

# RATES:

Australian calls: 0.014
Mobile calls: 0.012
National calls: 0.05
Local calls: 0.05
Other calls: 0.14

# EXCEPTIONS

- The Serivce Company
    - toll free (TFree Inbound) mobiele rates are 0.28, national rates are 0.1, Autraia and other are 0.14
    - Their rates for the others are the same as the others

- Sensium? TBC

# INVOICE CREATION

- Calulcate the mintues from the calls down to the second
    E.g. Australian Calls 7 Call, 00:23:24 = 24 minutes * 0.14 = $3.36
    or Mobile Calls 1 day 04:29:46 = (24 * 60) + (4 * 60) + 30 = 0.12 * 1710 = $205.20
- Sum each company total
- Collate each company total
- Go into Xero and create an invoice per company
    Invoice Line Description = Devoli Calling Charges with the Local, Mobile, National, Australian, and Other calls
    Account = 43850
    Qty 1 
    Price = Total
--- The Service Company has a different account description (IS10240 as an example)
        The lines are split per number e.g 366, TFree Inbound, etc
        $55 Base Fee ontop of the calling usage charges

# FUTURE 

- Handle UFB, DDIs, SIP lines