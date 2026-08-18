"""estimate_face_frontal_ratio: ước lượng mức độ "nhìn thẳng" của 1 khuôn mặt
từ 5 điểm mốc (kps) mà insightface luôn trả kèm mỗi Face (mắt trái, mắt
phải, mũi, khoé miệng trái, khoé miệng phải - thứ tự chuẩn SCRFD/RetinaFace,
xem core/ai_model_manager.py::detect_faces) - dùng để LỌC mặt quay nghiêng
quá nhiều TRƯỚC KHI xét nhận diện/Stranger.

Vì sao cần thêm cái này (ngoài det_score đã có): det_score đo "có chắc đây
là 1 khuôn mặt hay không" - 1 khuôn mặt quay nghiêng vẫn có thể có det_score
RẤT CAO (detector vẫn nhận ra rõ ràng đó là mặt người), NHƯNG embedding
ArcFace tính từ góc nghiêng đó kém tin cậy hơn nhiều so với ảnh thẳng, khiến
similarity với chính người đó (đã đăng ký bằng ảnh thẳng) tụt xuống rất thấp
- có thể tụt hẳn qua ngưỡng "chắc chắn Stranger" dù đó vẫn là người quen chỉ
đang quay đầu. det_score một mình KHÔNG lọc được trường hợp này - cần thêm
ước lượng góc mặt riêng."""
from __future__ import annotations

from typing import Optional

import numpy as np


def estimate_face_frontal_ratio(kps: Optional[np.ndarray]) -> float:
    """kps: mảng (5,2) [mắt trái, mắt phải, mũi, khoé miệng trái, khoé miệng
    phải]. Trả về tỉ lệ khoảng cách mũi<->mắt GẦN/khoảng cách mũi<->mắt XA
    (0..1) - không phụ thuộc việc gán đúng "trái"/"phải" (chỉ cần đúng 2 mắt
    + mũi, min/max tự đối xứng). Mặt nhìn thẳng: mũi gần như cách đều 2 mắt
    -> tỉ lệ gần 1.0. Mặt quay nghiêng: mũi lệch hẳn về phía 1 mắt (gần mắt
    này, xa mắt kia) -> tỉ lệ giảm dần về 0 khi nghiêng tới gần 90 độ.

    Thiếu/hỏng kps -> trả về 1.0 (coi như thẳng, KHÔNG lọc) - an toàn hơn là
    lọc nhầm 1 mặt hợp lệ chỉ vì thiếu dữ liệu landmark."""
    if kps is None or len(kps) < 3:
        return 1.0
    left_eye, right_eye, nose = np.asarray(kps[0]), np.asarray(kps[1]), np.asarray(kps[2])
    dist_to_left = float(np.linalg.norm(nose - left_eye))
    dist_to_right = float(np.linalg.norm(nose - right_eye))
    farther = max(dist_to_left, dist_to_right)
    if farther <= 0:
        return 1.0
    return min(dist_to_left, dist_to_right) / farther
