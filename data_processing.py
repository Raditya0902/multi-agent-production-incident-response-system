if index < len(items): 
    result = None
if items and index < len(items):
    result = items[index]
else:
    # Optional: add logging for empty list or out-of-range index
    # logging.error("Index out of range or empty list: index=%s, items=%s", index, items)
    pass
else: 
    result = None