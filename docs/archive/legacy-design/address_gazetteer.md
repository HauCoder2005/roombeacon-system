> **ARCHIVED** — superseded by [ADDRESS_AND_ADMIN_NORMALIZATION.md](../../04-processing/ADDRESS_AND_ADMIN_NORMALIZATION.md).

# Cơ Chế Xử Lý Địa Chỉ Bằng Gazetteer (Full-text Aho-Corasick)

## 1. Vấn Đề Gốc
Trước đây, bộ Address Parser (`notebooks/utils/address_parser.py`) sử dụng các biểu thức chính quy (Regex) cắt chuỗi theo dấu phẩy và kiểm tra tiền tố hành chính (`Quận`, `Huyện`, `Phường`, `Xã`). 
Cách tiếp cận này gặp phải 3 lỗi lớn khi đối mặt với dữ liệu thực tế (đặc biệt từ Phongtro123, Cafeland):
1. **Mất từ khóa hành chính:** Dữ liệu viết tắt "Bình Thạnh, TP.HCM", mất chữ "Quận", khiến Regex bỏ qua hoàn toàn.
2. **Sai cấp bậc hành chính:** Nguồn ghi "Phường Gò Vấp", "Phường Tân Bình". Regex bắt trúng chữ "Phường" nên cắt nhầm Quận mang sang gán cho Phường.
3. **Tên địa danh cũ / dị biệt:** "Thạnh Mỹ Tây", "An Nhơn", "Bảy Hiền" không được map về phường chuẩn.

## 2. Giải Pháp: Gazetteer Quét Toàn Văn
Phương án **Gazetteer + Maximal Munch (tương đương Aho-Corasick)** được áp dụng để giải quyết triệt để vấn đề:
- Không cắt chuỗi theo dấu phẩy.
- Không phụ thuộc vào tiền tố hành chính.
- Map tự động alias (tên cũ, viết tắt, sai sót) về tên chuẩn (Canonical Name).

### 2.1 Cấu Trúc Dictionary
Bảng từ điển (Gazetteer) bao gồm danh sách Quận/Huyện và Phường/Xã chuẩn của TP.HCM, kèm theo các alias phổ biến:
```python
HCM_DISTRICTS = {
    "Quận Bình Thạnh": ["Quận Bình Thạnh", "Q. Bình Thạnh", "Bình Thạnh", "Phường Bình Thạnh"], # Bắt luôn lỗi Phường Bình Thạnh
    "Quận Gò Vấp": ["Quận Gò Vấp", "Gò Vấp", "Phường Gò Vấp"],
    ...
}

HCM_WARDS = {
    "Quận Bình Thạnh": {
        "Phường 27": ["Phường 27", "Thạnh Mỹ Tây", "Phường Thạnh Mỹ Tây"]
    }
}
```

### 2.2 Cơ Chế Hoạt Động Của Code
Thuật toán được bọc trong class `FullTextGazetteer`. 
1. **Khởi tạo:** Class nhận toàn bộ dictionary. Nó lưu lại kiểu thực thể (`DISTRICT`, `WARD`), tên chuẩn (`name`), và thông tin Quận cha (`parent` đối với Ward).
2. **Compile:** Thuật toán sắp xếp tất cả các alias theo độ dài giảm dần (để ưu tiên bắt cụm từ dài nhất trước - Longest Match) và compile thành 1 Regex lớn sử dụng `|` (alternation) kèm ranh giới từ `\b`.
3. **Extract:** Quét chuỗi `full_address_text` một lần duy nhất (`O(N)`). 
    - Nếu tìm thấy 1 alias thuộc `WARD` (VD: "Thạnh Mỹ Tây"), nó sẽ tự động chốt tên Phường là "Phường 27", và **tự động chốt luôn tên Quận** là "Quận Bình Thạnh" (dựa vào `parent`).
    - Nếu tìm thấy alias thuộc `DISTRICT` (VD: "Bình Thạnh"), nó sẽ điền vào Quận (nếu chưa có Ward nào thiết lập Quận trước đó).

## 3. Đặc Điểm Nổi Bật
- **Deterministic:** Một input luôn ra đúng một output. Dễ dàng audit và debug.
- **Offline & Nhanh:** Chạy 100% bằng regex tối ưu của Python, không gọi API ngoài, xử lý hàng triệu dòng chỉ trong vài giây.
- **Dễ Maintain:** Khi có dòng map sai, Data Engineer chỉ cần thêm alias mới vào dictionary `HCM_DISTRICTS` hoặc `HCM_WARDS` mà không cần chạm vào logic regex phức tạp.

## 4. Tích hợp Bảng Sáp Nhập Phường (Phân giải Tên cũ/mới)
Hệ thống Gazetteer không chỉ chứa các tên hiện hành, mà đã được tự động tích hợp danh sách sáp nhập/đổi tên hành chính mới nhất (VD: Sáp nhập Phường ở TP.HCM năm 2024).
- **Data Source:** Toàn bộ bảng mapping sáp nhập phường được parse tự động thành file từ điển `notebooks/enums/ward_gazetteer.py`.
- **Hoạt động:** Khi Regex quét trúng một alias cũ (VD: "Phường Đa Kao"), nó sẽ tự động chốt tên chuẩn mới (Canonical Name) là "Phường Sài Gòn" theo đúng quy định hành chính hiện hành.
