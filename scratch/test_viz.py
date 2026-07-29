import sys
sys.path.insert(0, '.')
import pandas as pd
import numpy as np
from utils import viz_utils as vu

df = pd.DataFrame({
    'age': [25, 30, 35, 40, np.nan, 50, 55],
    'salary': [50000, 60000, 70000, 80000, 90000, np.nan, 110000],
    'gender': ['M', 'F', 'M', 'F', 'M', 'F', 'M'],
    'city': ['NYC', 'LA', 'NYC', 'Chicago', 'LA', 'NYC', 'Chicago']
})

print("Testing histogram...")
fig1 = vu.histogram(df, 'age')
print("Histogram JSON len:", len(fig1.to_json()))

print("Testing scatter...")
fig2 = vu.scatter_plot(df, 'age', 'salary')
print("Scatter JSON len:", len(fig2.to_json()))

print("Testing correlation...")
fig3 = vu.correlation_heatmap(df, ['age', 'salary'])
print("Correlation JSON len:", len(fig3.to_json()))

print("Testing missing...")
fig4 = vu.missing_bar(df)
print("Missing JSON len:", len(fig4.to_json()))

print("All charts generated successfully!")
