import pandas as pd

# Create a sample dataframe
data = {
    'Product': ['Consulting Services', 'Software License', 'Support Package'],
    'Quantity': [10, 5, 1],
    'Price': [150.00, 299.99, 500.00]
}

df = pd.DataFrame(data)

# Save to Excel
df.to_excel('sample_invoice_data.xlsx', index=False)

print("Created sample_invoice_data.xlsx")
