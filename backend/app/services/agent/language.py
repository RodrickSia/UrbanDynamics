"""EN/VI reply language, including short replies and user-only history."""
import re


def hint(message):
    lower=message.casefold()
    if re.search(r'(reply|respond|answer|translate).{0,20}(in|to) english|trả lời.{0,15}tiếng anh',lower):return 'English'
    if re.search(r'(reply|respond|answer|translate).{0,20}(in|to) vietnamese|trả lời.{0,15}tiếng việt',lower):return 'Vietnamese'
    # These short replies are unambiguously English even without a full sentence.
    if re.fullmatch(r'\s*(yes|no|yep|yeah|nope|sure|continue|proceed|thanks|thank you|why|how|go ahead)[.!?\s]*',lower):return 'English'
    english=len(re.findall(r'\b(find|within|visible|map|show|compare|those|these|the|and|with|price|parcels|travel|driving|route|source|count|please|explain|selected|building|results|why|how|can|could|would|should|is|are|does|what|where|when)\b',lower))
    vietnamese=len(re.findall(r'\b(tôi|mình|hãy|tìm|những|giá|đất|tiếp tục|trong|vùng|diện tích|hiển thị|đường|giữ|điều kiện|cho tôi|bỏ|thửa)\b',lower))
    if english>=3 and english>vietnamese:return 'English'
    if vietnamese>=2 or re.search('[ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]',lower):return 'Vietnamese'
    return 'English' if english>=2 else None


def resolve(message, history):
    """Current explicit/detectable language wins; neutral replies inherit users.

    Do not infer from assistant/tool text: an earlier wrong-language answer must
    not propagate itself. Existing sessions need no stored-language migration.
    """
    current = hint(message)
    if current:
        return current
    if re.fullmatch(r'\s*(ok(?:ay)?|[0-9]+|👍|👌|✅)[.!?\s]*',message.casefold()):
        for item in reversed(history):
            if item.get('role') == 'user':
                previous = hint(item.get('content',''))
                if previous:
                    return previous
    return None
