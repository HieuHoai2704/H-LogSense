# academic/ — research and coursework

Material that supports the thesis and course, kept apart from the product. Nothing in `app/` or `scripts/`
imports from here, and none of it is packaged in the wheel or the download ZIPs. Code here may use `app` and
`scripts` (for example the HDFS experiment uses the product parser).

| Folder | Contents |
| --- | --- |
| [`literature/`](literature/README.md) | Paper library by topic, registry, reviews and reports (PDFs stay local, ignored by Git) |
| [`notes/`](notes/README.md) | Dataset catalog, paper list, baseline reviews and measured dataset runs |
| `tools/` | `python -m academic.tools.download_research`, `python -m academic.tools.inspect_research_archives` — collect public papers and datasets into `data/` |
| `experiments/` | Baselines the product does not use: `hdfs_analysis.py` (HDFS block sessions) run by `python -m academic.experiments.hdfs_baseline` ([notes](notes/HDFS_BLOCK_BASELINE_VI.md)) |
| `tests/` | Tests for the experiments: `python -B -m unittest discover -s academic -t .` |
| `course/` | Course reports, slides and lab scripts, e.g. `python -m academic.course.mysql_course_lab` |

Install the course extras with `pip install -e ".[course]"`. Downloaded datasets and papers go to `data/raw/` and `data/research/`, both ignored by Git.
