-include config.mk

BOOK ?= cpp_idioms
BUILD_DIR := make_output
AI_DISCLOSURE := AI-Generated Content: Drafted by LLM, Structured by Human.

CHAPTERS ?= $(sort $(wildcard [0-9]*.md chapter_*.md)) $(sort $(wildcard appendix*.md))

METADATA_FILE=00-metadata.yaml
PANDOC_COMMON_OPTS= --metadata-file=$(METADATA_FILE) $(CHAPTERS) \
                    --toc \
                    --highlight-style kate \
                    --verbose \
                    --metadata "identifier:urn:uuid:$(shell uuidgen)"

MAIN_FONT := "Noto Serif"
MONO_FONT := "Noto Sans Mono"
DOC_CLASS := extbook
FONT_SIZE := 11pt
GEOMETRY_OPTS := paperwidth=6.14in,paperheight=9.21in,lmargin=0.55in,rmargin=0.55in,bindingoffset=0.25in,tmargin=0.7in,bmargin=0.7in

.PHONY: all epub pdf docx generate_mermaid_images clean pretty view check make_tmp_dir

# Use a stamp file to track formatting
PRETTY_STAMP = .formatted

# The stamp file depends on the markdown files
$(PRETTY_STAMP): $(CHAPTERS)
	prettier --parser markdown --embedded-language-formatting off --write $(CHAPTERS) \
	&& sed -i '/<!-- prettier-ignore -->/d' $(CHAPTERS)
	touch $(PRETTY_STAMP)

generate_mermaid_images:
	python3 generate_mermaid_images.py || exit 1

all: epub pdf

epub: $(BOOK).epub

pdf: $(BOOK).pdf

docx: $(BOOK).docx

make_tmp_dir:
	@mkdir -p $(BUILD_DIR)

# The epub and pdf targets depend on the stamp file
$(BOOK).epub: generate_mermaid_images $(METADATA_FILE) $(CHAPTERS) $(PRETTY_STAMP) make_tmp_dir
	pandoc $(PANDOC_COMMON_OPTS) \
	       -o $@ \
	       --to=epub2 \
	       --css=epub-fix.css \
	       --from markdown-task_lists-smart \
	       --log $(BUILD_DIR)/generate_pandoc_epub.log
			# Inject AI metadata into PDF
			# exiftool -overwrite_original -XMP-dc:Description="$(AI_DISCLOSURE)" $(BOOK).epub

$(BOOK).pdf: generate_mermaid_images $(METADATA_FILE) $(CHAPTERS) $(PRETTY_STAMP) make_tmp_dir
	@echo "Generating PDF..." | tee $(BUILD_DIR)/log_make_pdf.log
	pandoc $(PANDOC_COMMON_OPTS) \
	       -o $@ \
	       --pdf-engine=xelatex \
	       --pdf-engine-opt=-output-directory=$(BUILD_DIR) \
	       --listings \
	       -H code-wrapping.tex \
	       -H listings-setup.tex \
	       -H headers-setup.tex \
	       --top-level-division=chapter \
	       -V mainfont=$(MAIN_FONT) \
	       -V monofont=$(MONO_FONT) \
	       -V documentclass=$(DOC_CLASS) \
	       -V geometry:"$(GEOMETRY_OPTS)" \
	       -V linestretch=1.25 \
	       -V fontsize=$(FONT_SIZE) \
	       --log $(BUILD_DIR)/generate_pandoc_pdf.log
	# Inject AI metadata into PDF
	exiftool -overwrite_original -XMP-dc:Description="$(AI_DISCLOSURE)" $(BOOK).pdf

$(BOOK).docx: generate_mermaid_images $(METADATA_FILE) $(CHAPTERS) $(PRETTY_STAMP) make_tmp_dir
	pandoc $(PANDOC_COMMON_OPTS) \
	       -o $@ \
	       --log $(BUILD_DIR)/$@.log
	# exiftool -overwrite_original -Description="$(AI_DISCLOSURE)" $(BOOK).docx
	python3 update_docx_toc.py $@

# Remember to clean up the stamp file
clean:
	rm -f $(BOOK).epub
	rm -f $(BOOK).docx
	rm -f $(BOOK).pdf
	rm -f $(PRETTY_STAMP)
	rm -f *.log
	rm -rf $(BUILD_DIR)

# pretty:
# 	find . -name '*.md' -exec python format_md_codeblocks.py {} \; \
# 	&& prettier --embedded-language-formatting off --write *.md \
# 	&& sed -i '/<!-- prettier-ignore -->/d' *.md


view:
	ebook-viewer ./$(BOOK).epub &


check: $(BOOK).epub
	epubcheck ./$(BOOK).epub
