# Demo Files

This folder contains sample documents for testing the indexing pipeline.

## Files

### demo_BG.csv
- **Description:** 4 Bulgarian property listings (недвижимость в Болгарии)
- **Columns:** Название, Город, Цена (€), Комнат, Площадь (м²), Этаж, Этажей, До моря (м), Поддержка (€), Санузлов, Мебель, Круглогодичность, Описание, Ссылка
- **Format:** CSV with UTF-8 encoding
- **Size:** ~1.8 KB

### info_bg_home.docx
- **Description:** Company contact information (контакты компании BG-HOME)
- **Content:** Office locations in Bulgaria, Russia, Ukraine, Poland, Kazakhstan, Belarus, USA
- **Format:** DOCX (Microsoft Word)
- **Size:** ~1.7 MB

## Usage

Index both files to Qdrant:

```bash
python simple_index_test.py \
    data/demo/demo_BG.csv \
    data/demo/info_bg_home.docx \
    --collection bulgarian_properties \
    --recreate
```

## Result

- **Collection:** `bulgarian_properties`
- **Total chunks:** 2 (1 per file with current settings)
- **Vectors:** BGE-M3 (dense 1024-dim + BM42 sparse + ColBERT)
- **Format:** n8n/LangChain compatible (`page_content` + `metadata`)

## Note

This folder is excluded from Git (see `.gitignore`) to avoid committing large binary files.
