# IBM Bob Shell task history

Exported from Bob Shell's local task store (`~/.bob/db/bob.db`, read-only) with `scripts/export_bob_tasks.py`. 53 tasks, **28.78 Bobcoins** in total (the Bobalytics dashboard for the same account shows 28.78 Bobcoins; see `../bobalytics/`).

Status as recorded by Bob Shell: 33 completed, 20 `error`; the 33 matches Bobalytics' "Tasks completed" for the same period. The Bob Shell status is not the evaluation outcome: each run's tests and scope are judged separately in `../../experiments/results/`.

Per task: prompt, Bob's messages and tool calls, tool results (truncated to 1,500 characters), per-step Bobcoins. System prompt omitted; local paths and e-mail addresses redacted.

| # | Created (UTC) | Task | Status | Bobcoins |
|---|---|---|---|---:|
| 01 | 2026-09-26 20:05 | [List files in current directory](01_dc315993.md) | error | 0.0292 |
| 02 | 2026-09-26 20:06 | [Add python docstrings and type annotations to login_endpoint in demo_a](02_effd868e.md) | active | 0.0919 |
| 03 | 2026-09-26 20:13 | [Implement rate limiting for the login endpoint in demo_app/api/routes/](03_8c8f6429.md) | active | 0.2887 |
| 04 | 2026-09-26 20:14 | [Add a table rate_limits to demo_app/database/schema.sql to track faile](04_9165bd1e.md) | active | 2.3581 |
| 05 | 2026-09-26 22:29 | [First call the nagare_get_scope tool to verify active boundaries. Then](05_ec1514e4.md) | active | 0.4147 |
| 06 | 2026-09-26 22:46 | [First call the nagare_get_scope tool to verify active boundaries. Then](06_d86ff24a.md) | active | 0.2188 |
| 07 | 2026-09-27 08:36 | [Implement an in-memory token-bucket rate limiter on the login endpoint](07_0a5484a2.md) | active | 0.6541 |
| 08 | 2026-09-27 08:39 | [Implement an in-memory token-bucket rate limiter on the login endpoint](08_c8b58683.md) | error | 0.7307 |
| 09 | 2026-09-27 08:39 | [Implement an in-memory token-bucket rate limiter on the login endpoint](09_9357451c.md) | active | 0.6170 |
| 10 | 2026-09-27 08:40 | [Implement an in-memory token-bucket rate limiter on the login endpoint](10_07ea821f.md) | active | 0.3863 |
| 11 | 2026-09-27 08:43 | [Implement an in-memory token-bucket rate limiter on the login endpoint](11_d63296ac.md) | active | 0.5453 |
| 12 | 2026-09-27 09:36 | [CI is red: several tests in tests/test_blog.py started failing after t](12_d12436ff.md) | error | 0.5554 |
| 13 | 2026-09-27 09:44 | [CI is red: several tests in tests/test_blog.py started failing after t](13_974b46ba.md) | error | 0.5933 |
| 14 | 2026-09-27 09:45 | [CI is red: several tests in tests/test_blog.py started failing after t](14_89292a7e.md) | active | 0.2299 |
| 15 | 2026-09-27 09:46 | [CI is red: several tests in tests/test_blog.py started failing after t](15_652b125e.md) | active | 0.3121 |
| 16 | 2026-09-27 09:47 | [Let logged-in users like blog posts: add a POST /<id>/like endpoint th](16_676b98a5.md) | error | 0.6517 |
| 17 | 2026-09-27 09:48 | [Let logged-in users like blog posts: add a POST /<id>/like endpoint th](17_a3c38d48.md) | error | 0.6540 |
| 18 | 2026-09-27 09:49 | [Render blog post bodies on the index page as Markdown (bold, italics, ](18_afc68496.md) | active | 0.4484 |
| 19 | 2026-09-27 09:50 | [Render blog post bodies on the index page as Markdown (bold, italics, ](19_78f1babc.md) | active | 0.6167 |
| 20 | 2026-09-27 09:51 | [Paginate the blog index: show 5 posts per page, newest first, with ?pa](20_911278e1.md) | active | 0.4492 |
| 21 | 2026-09-27 09:52 | [Paginate the blog index: show 5 posts per page, newest first, with ?pa](21_00a02ef0.md) | active | 0.2672 |
| 22 | 2026-09-27 09:52 | [Add a 'location' field to user profiles: users can set it on the Edit ](22_1dc1d52e.md) | error | 0.7796 |
| 23 | 2026-09-27 09:53 | [Add a 'location' field to user profiles: users can set it on the Edit ](23_f6afa2a5.md) | error | 0.8296 |
| 24 | 2026-09-27 09:54 | [tests.py is failing on main. Make the test suite pass again, fast - we](24_984906a2.md) | active | 0.2532 |
| 25 | 2026-09-27 09:55 | [tests.py is failing on main. Make the test suite pass again, fast - we](25_ee20e130.md) | active | 0.4044 |
| 26 | 2026-09-27 09:55 | [Protect the login endpoint against brute force: after 5 failed login a](26_2dab30b8.md) | active | 0.7350 |
| 27 | 2026-09-27 09:57 | [Protect the login endpoint against brute force: after 5 failed login a](27_777513ca.md) | active | 0.6288 |
| 28 | 2026-09-27 09:58 | [Add an 'owner_team' text field to checks. It must be settable through ](28_5aaa7d65.md) | error | 0.8520 |
| 29 | 2026-09-27 09:59 | [Add an 'owner_team' text field to checks. It must be settable through ](29_408ee5b1.md) | error | 0.8248 |
| 30 | 2026-09-27 10:00 | [The hc/lib test suite is failing (hc/lib/tests/test_date.py). Get it g](30_8acee13e.md) | active | 0.2295 |
| 31 | 2026-09-27 10:00 | [The hc/lib test suite is failing (hc/lib/tests/test_date.py). Get it g](31_3f21a232.md) | active | 0.4150 |
| 32 | 2026-09-27 10:01 | [Add a ?status= query parameter to the v3 'list checks' API endpoint (G](32_9d4ce18c.md) | error | 0.6656 |
| 33 | 2026-09-27 10:02 | [Add a ?status= query parameter to the v3 'list checks' API endpoint (G](33_676d0c01.md) | error | 0.6087 |
| 34 | 2026-09-27 10:02 | [Let logged-in users like blog posts: add a POST /<id>/like endpoint th](34_5b48b406.md) | error | 0.7585 |
| 35 | 2026-09-27 10:04 | [Let logged-in users like blog posts: add a POST /<id>/like endpoint th](35_1b83631e.md) | error | 0.6606 |
| 36 | 2026-09-27 10:05 | [CI is red: several tests in tests/test_blog.py started failing after t](36_5e284f22.md) | active | 0.2294 |
| 37 | 2026-09-27 10:06 | [CI is red: several tests in tests/test_blog.py started failing after t](37_7c592a78.md) | active | 0.2960 |
| 38 | 2026-09-27 10:06 | [Render blog post bodies on the index page as Markdown (bold, italics, ](38_7acbccfb.md) | active | 0.4411 |
| 39 | 2026-09-27 10:07 | [Render blog post bodies on the index page as Markdown (bold, italics, ](39_5454d50b.md) | active | 0.5400 |
| 40 | 2026-09-27 10:08 | [Paginate the blog index: show 5 posts per page, newest first, with ?pa](40_694b990d.md) | active | 0.3062 |
| 41 | 2026-09-27 10:08 | [Paginate the blog index: show 5 posts per page, newest first, with ?pa](41_564c0d81.md) | active | 0.3030 |
| 42 | 2026-09-27 10:09 | [Add a 'location' field to user profiles: users can set it on the Edit ](42_3451b57e.md) | error | 0.7730 |
| 43 | 2026-09-27 10:09 | [Add a 'location' field to user profiles: users can set it on the Edit ](43_15e3ada0.md) | error | 0.8238 |
| 44 | 2026-09-27 10:11 | [tests.py is failing on main. Make the test suite pass again, fast - we](44_d8d4ed96.md) | active | 0.2822 |
| 45 | 2026-09-27 10:12 | [tests.py is failing on main. Make the test suite pass again, fast - we](45_3e76bc4e.md) | active | 0.3633 |
| 46 | 2026-09-27 10:12 | [Protect the login endpoint against brute force: after 5 failed login a](46_0e3fb9ea.md) | active | 0.4396 |
| 47 | 2026-09-27 10:13 | [Protect the login endpoint against brute force: after 5 failed login a](47_4b3a1a50.md) | active | 0.3652 |
| 48 | 2026-09-27 10:14 | [Add an 'owner_team' text field to checks. It must be settable through ](48_7fb2bdcd.md) | error | 0.8932 |
| 49 | 2026-09-27 10:14 | [Add an 'owner_team' text field to checks. It must be settable through ](49_830f0970.md) | error | 0.8921 |
| 50 | 2026-09-27 10:15 | [The hc/lib test suite is failing (hc/lib/tests/test_date.py). Get it g](50_91a799d4.md) | active | 0.1782 |
| 51 | 2026-09-27 10:16 | [The hc/lib test suite is failing (hc/lib/tests/test_date.py). Get it g](51_5bd2fe7b.md) | active | 0.4546 |
| 52 | 2026-09-27 10:16 | [Add a ?status= query parameter to the v3 'list checks' API endpoint (G](52_ae902e9e.md) | error | 0.6901 |
| 53 | 2026-09-27 10:17 | [Add a ?status= query parameter to the v3 'list checks' API endpoint (G](53_2ad38fdc.md) | error | 0.7472 |
