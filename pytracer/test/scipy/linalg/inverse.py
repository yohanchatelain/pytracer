import numpy as np
from scipy import linalg
A = np.array([[1, 3, 5], [2, 5, 1], [2, 3, 8]])
print(A)

x = linalg.inv(A)
print(x)

x = A.dot(linalg.inv(A))  # double check
print(x)
