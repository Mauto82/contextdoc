# Agents with and without ContextDoc — model haiku, 3 run(s) each

| Task | none | ctx | ctx+claude | ctx+hook |
|---|---|---|---|---|
| T1-bcrypt | 2/3 | 1/3 | 0/3 | 0/3 |
| T2-hard-delete | 3/3 | 3/3 | 0/3 | 1/3 |
| T3-id-reuse | 1/3 | 2/3 | 0/3 | 1/3 |
| T4-atomic-save | 3/3 | 3/3 | 0/3 | 0/3 |
| **all** | **9/12** | **9/12** | **0/12** | **2/12** |

Cells: runs that violated the tension / valid runs. conceptualTests modified in 0 run(s); 0 run(s) failed to complete.
