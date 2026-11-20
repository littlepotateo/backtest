# Error codes

Every error the dashboard shows ends with a code such as `BT-PDF-002`. Quote it when asking for help.
Codes are stable: a code never changes meaning. The test suite checks that every code used in the program is listed here.

## Page and server (`BT-HTTP`, `BT-JS`, `BT-TASK`, `BT-SET`)

| Code | Meaning | What to do |
|---|---|---|
| BT-HTTP-400 | The page sent a request the server could not understand. | Refresh the page. |
| BT-HTTP-403 | The request came from a different website or address than the dashboard. | Open the dashboard at the address printed when it started. |
| BT-HTTP-404 | The server has no such feature. The server is almost always an older version than the page. | Close the dashboard and start it again with `start.sh` (Mac: `Start Backtester.command`, Windows: `start.bat`). The footer shows the server version. |
| BT-HTTP-405 | The server knows that address but not for that kind of request (page and server are different versions). | Restart as for BT-HTTP-404. |
| BT-HTTP-500 | An unexpected bug or a missing package inside the server. | Read the terminal window running the dashboard; restart with `start.sh`. |
| BT-JS-001 | A script on the page failed. | Refresh; if it persists, restart the dashboard. |
| BT-JS-002 | A background step on the page failed without a message. | Refresh and try again. |
| BT-NET-000 | The page could not reach the dashboard server. | Check the server is still running. |
| BT-TASK-500 | A background job (download, run) hit a bug. | Open the Activity log of the job for details. |
| BT-SET-001 | A saved key did not look like a key. | Paste it again without spaces. |

## Fallback codes

`BT-ERR-000`, `BT-PDF-000`, `BT-REQ-000`, `BT-SRCH-000` and `BT-CLAUDE-000` are used only when an error has no more specific code. Read the message, and tell me the code and the message.

## Papers (`BT-PDF`, `BT-REQ`, `BT-SRCH`)

| Code | Meaning | What to do |
|---|---|---|
| BT-PDF-001 | The PDF is larger than 60 MB. | Use a smaller file. |
| BT-PDF-002 | The file is not a PDF (does not start with the PDF marker). | Re-download the paper. |
| BT-PDF-003 | The PDF reader (`pypdf`) is not installed. | Restart with `start.sh`, which installs it. |
| BT-PDF-004 | The PDF is password-protected. | Remove the password and drop it again. |
| BT-PDF-005 | The PDF is damaged or in a form that cannot be read. | Re-download it or print it to a new PDF. |
| BT-PDF-006 | The dropped file does not have a `.pdf` name. | Drop PDF files only. |
| BT-PDF-007 | Nothing was dropped. | Drop at least one PDF. |
| BT-REQ-001 | The Consensus search request was empty or too short. | Describe the topic. |
| BT-REQ-002 | The request was too long. | Shorten it. |
| BT-SRCH-001 | OpenAlex search text shorter than three characters. | Type more. |
| BT-SRCH-002 | OpenAlex search text longer than 200 characters. | Shorten it. |
| BT-SRCH-003 | OpenAlex sent a reply that could not be read. | Try again. |
| BT-SRCH-401 | OpenAlex did not accept the saved key. | Check it under OpenAlex settings. |
| BT-SRCH-429 | OpenAlex's free allowance for your network is used up (it is shared per network address). | Save a free key under OpenAlex settings, or use Consensus through Claude. |
| BT-SRCH-500 | OpenAlex returned another HTTP error. | Try again later. |

## Claude Code jobs (`BT-CLAUDE`)

| Code | Meaning | What to do |
|---|---|---|
| BT-CLAUDE-001 | Claude Code (the `claude` program) was not found on this computer. | Install it and sign in once by typing `claude` in a terminal (https://code.claude.com/docs), then restart the dashboard. If it is installed in an unusual place, set the environment variable `BACKTEST_CLAUDE` to its full path. |
| BT-CLAUDE-002 | Claude Code could not start, stopped without an answer, reported an error, or ran past the time limit (10 minutes). | Read the message; try again, or use a shorter paper. |
| BT-CLAUDE-003 | Claude Code is installed but not signed in. | Type `claude` in a terminal and sign in, then try again. |
| BT-CLAUDE-004 | Claude Code cannot reach Consensus. | Add the Consensus connector at claude.ai/settings/connectors, start `claude` once to sign in, then try again. OpenAlex search works without it. |
| BT-CLAUDE-005 | Claude's reply could not be used (not valid JSON, no summary, no papers), or the paper has nothing to analyse. | Try again; for a paper with no text, drop its PDF first. |

## Data and downloads (`BT-DATA`, `BT-NET`)

| Code | Meaning | What to do |
|---|---|---|
| BT-DATA-000 | A data problem with no more specific code. | Read the message. |
| BT-DATA-001 | Yahoo returned no bars for that symbol and period. | Check the ticker and dates. |
| BT-DATA-002 | The downloaded data failed validation. | Try again, or use another source. |
| BT-DATA-003 | Unsupported bar size. | Choose one from the list. |
| BT-DATA-004 | No symbol, or text that does not look like a ticker. | Enter tickers such as SPY. |
| BT-DATA-005 | More than 40 symbols at once. | Fetch fewer. |
| BT-DATA-006 | Could not tell which symbol an imported file holds. | Enter the symbol and import again. |
| BT-DATA-007 | Only `.csv` and `.json` price files can be imported (or none were dropped). | Drop a price file. |
| BT-DATA-008 | An imported file could not be read as price data. | Check its columns. |
| BT-DATA-009 | That symbol and bar size are not in the cache. | Download it on the Data page. |
| BT-DATA-010 | A date was not in the form 2005-01-31. | Correct the date. |
| BT-DATA-011 | One or more items in a batch failed; the message lists each. | Read the list. |
| BT-DATA-012 | Imported files are larger than 200 MB in total. | Import fewer at once. |
| BT-DATA-013 | One or more setup checks failed. | Read the check lines. |
| BT-NET-001 | Could not reach the data or search service. | Check the internet connection. |
| BT-NET-002 | The secure connection could not be verified (certificate error). | See the message: install certificates or check a company VPN. |
| BT-NET-003 | The service did not answer in time. | Check the connection, VPN or firewall. |
| BT-NET-004 | The service's address could not be found (offline or DNS). | Check that this computer is online. |
| BT-NET-005 | The service sent a reply that could not be read. | Try again in a minute. |
| BT-NET-006 | The service reported an error for the request. | Read the message. |
| BT-NET-400 | The service rejected the request (for intraday bars it keeps only recent days). | Use a later start date. |
| BT-NET-404 | The service has no data for that symbol. | Check the ticker; index symbols start with `^`. |
| BT-NET-429 | The service is limiting requests. | Wait a minute and try again. |
| BT-NET-500 | The service returned another HTTP error. | Try again later. |

## Project files (`BT-LIB`, `BT-FILE`)

| Code | Meaning | What to do |
|---|---|---|
| BT-LIB-000 | The paper library files cannot be read (no more specific code). | Read the message. |
| BT-LIB-001 | `research/library/index.json` is damaged and cannot be read. | Open it in a text editor to fix it, or rename it to start an empty library; saved PDFs are kept. |
| BT-FILE-001 | A file could not be read or written because of a text-encoding problem (typical on Windows with letters such as the "fi" ligature in a paper). | Restart with `start.bat` / `start.sh`, which switch the program to UTF-8. |

## Backtest runs (`BT-RUN`)

These appear on the run status page. The page says which of the four it is in plain words; the code lets you look it up.

| Code | Meaning | What to do |
|---|---|---|
| BT-RUN-001 | Your strategy's own code raised an error, so no result was saved. The page names the file and line. | Fix the strategy file at that line and run again. |
| BT-RUN-002 | The settings cannot be used: bad dates, no data for the symbol, an unknown parameter, and similar. Nothing was run. | Change the setting the message names, or download the data, and run again. |
| BT-RUN-003 | The program hit an internal error while completing the analysis. Your strategy's code did not raise it. | Copy the technical details and report the code. |
| BT-RUN-004 | The run took longer than 30 minutes and was stopped. | Use a shorter date range or fewer validation paths. |

A run that finishes and is saved is not an error, even when the strategy lost money. The status page then gives a separate "Strategy result" line (lost money, lagged buy and hold, beat it, or made no trades).
