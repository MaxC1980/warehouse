from flask import request

def get_per_page(default=20, max_value=100):
    per_page = request.args.get('per_page', default, type=int)
    return min(per_page, max_value)
