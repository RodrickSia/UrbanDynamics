"""Small EN/VI hint for the current turn; place names do not set reply language."""
import re


def hint(message):
    lower=message.casefold()
    if re.search(r'(reply|respond|answer|translate).{0,20}(in|to) english|trả lời.{0,15}tiếng anh',lower):return 'English'
    if re.search(r'(reply|respond|answer|translate).{0,20}(in|to) vietnamese|trả lời.{0,15}tiếng việt',lower):return 'Vietnamese'
    english=len(re.findall(r'\b(find|within|visible|map|show|compare|those|these|the|and|with|price|parcels|travel|driving|route|source|count|please)\b',lower))
    vietnamese=len(re.findall(r'\b(tôi|mình|hãy|tìm|những|giá|đất|tiếp tục|trong|vùng|diện tích|hiển thị|đường|giữ|điều kiện|cho tôi|bỏ|thửa)\b',lower))
    if english>=3 and english>vietnamese:return 'English'
    if vietnamese>=2 or re.search('[ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]',lower):return 'Vietnamese'
    return 'English' if english>=2 else None
