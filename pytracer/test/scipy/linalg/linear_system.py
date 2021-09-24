import numpy as np
from scipy import linalg
A = np.array([[1, 2], [3, 4]])
print(A)

b = np.array([[5], [6]])
print(b)

x = linalg.inv(A).dot(b)  # slow
print(x)

x = A.dot(linalg.inv(A).dot(b)) - b  # check
print(x)

x = np.linalg.solve(A, b)  # fast
print(x)

x = A.dot(np.linalg.solve(A, b)) - b  # check
print(x)
