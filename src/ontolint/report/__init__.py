"""
The reporters that render a QAResult as text: Markdown for a reader, CTRF for CI.

The third, the DQV report, is ontolint.dqv. All three are projections of the same
QAResult and none runs a check, so each is tested against a stored instance alone — see
design.md, *The three reporters are projections of QAResult*.
"""
