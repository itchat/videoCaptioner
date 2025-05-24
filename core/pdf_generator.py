"""
LaTeX风格的双语PDF生成器，专为播客和音频内容设计
"""
import os
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch, cm
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
import platform


class PodcastPDFGenerator:
    """专业的播客双语PDF生成器"""
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.setup_fonts()
        self.setup_styles()
        
    def setup_fonts(self):
        """设置中文字体支持"""
        try:
            # 尝试使用系统中文字体
            if platform.system() == "Darwin":  # macOS
                # 使用macOS系统字体
                font_paths = [
                    "/System/Library/Fonts/PingFang.ttc",
                    "/System/Library/Fonts/STHeiti Light.ttc",
                    "/System/Library/Fonts/Arial Unicode.ttf",
                ]
            else:  # Linux/Windows
                font_paths = [
                    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                    "/Windows/Fonts/msyh.ttc",  # Microsoft YaHei
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                        self.chinese_font = 'ChineseFont'
                        break
                    except Exception as e:
                        continue
            else:
                # 如果没有找到合适的字体，使用默认字体
                self.chinese_font = 'Helvetica'
                print("Warning: No Chinese font found, using Helvetica")
                
        except Exception as e:
            self.chinese_font = 'Helvetica'
            print(f"Font setup error: {e}")
    
    def setup_styles(self):
        """设置PDF样式"""
        styles = getSampleStyleSheet()
        
        # 标题样式 - LaTeX article风格
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=24,
            fontName=self.chinese_font,
            textColor=HexColor('#2c3e50'),
            spaceBefore=0.5*inch,
            spaceAfter=0.3*inch,
            alignment=TA_CENTER,
            leftIndent=0,
            rightIndent=0,
        )
        
        # 副标题样式
        self.subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=14,
            fontName=self.chinese_font,
            textColor=HexColor('#7f8c8d'),
            spaceBefore=0.1*inch,
            spaceAfter=0.4*inch,
            alignment=TA_CENTER,
        )
        
        # 章节标题样式
        self.section_style = ParagraphStyle(
            'CustomSection',
            parent=styles['Heading1'],
            fontSize=12,
            fontName=self.chinese_font,
            textColor=HexColor('#2c3e50'),
            spaceBefore=0.4*inch,
            spaceAfter=0.2*inch,
            leftIndent=0,
            borderWidth=0,
            borderColor=HexColor('#ecf0f1'),
            borderPadding=5,
        )
        
        # 英文正文样式
        self.english_style = ParagraphStyle(
            'EnglishBody',
            parent=styles['Normal'],
            fontSize=12,
            fontName='Times-Roman',
            textColor=HexColor('#2c3e50'),
            spaceBefore=0.1*inch,
            spaceAfter=0.05*inch,
            leftIndent=0,
            rightIndent=0,
            alignment=TA_JUSTIFY,
            leading=16,
        )
        
        # 中文正文样式
        self.chinese_style = ParagraphStyle(
            'ChineseBody',
            parent=styles['Normal'],
            fontSize=12,
            fontName=self.chinese_font,
            textColor=HexColor('#2c3e50'),
            spaceBefore=0.05*inch,
            spaceAfter=0.2*inch,
            leftIndent=0,
            rightIndent=0,
            alignment=TA_JUSTIFY,
            leading=16,
        )
        
        # 时间戳样式
        self.timestamp_style = ParagraphStyle(
            'Timestamp',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Courier',
            textColor=HexColor('#95a5a6'),
            spaceBefore=0.15*inch,
            spaceAfter=0.05*inch,
            leftIndent=0,
            alignment=TA_LEFT,
        )
        
        # 页脚样式
        self.footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            fontName=self.chinese_font,
            textColor=HexColor('#bdc3c7'),
            alignment=TA_CENTER,
        )
    
    def generate_pdf(self, transcript_entries, original_filename, translation_engine):
        """生成简洁的双语PDF文档"""
        # 创建输出文件名
        base_name = os.path.splitext(original_filename)[0]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"{base_name}_podcast_transcript_{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # 创建PDF文档
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=1*inch,
            leftMargin=1*inch,
            topMargin=1*inch,
            bottomMargin=1*inch,
        )
        
        # 构建文档内容 - 只包含正文
        story = []
        self._add_content(story, transcript_entries)
        
        # 生成PDF
        try:
            doc.build(story)
            return output_path
        except Exception as e:
            raise Exception(f"PDF generation failed: {str(e)}")
    
    def _add_title_page(self, story, filename, engine, entry_count):
        """添加LaTeX风格的标题页"""
        # 主标题
        clean_filename = os.path.splitext(filename)[0]
        story.append(Paragraph(f"Podcast Transcript", self.title_style))
        story.append(Paragraph(f"播客转录", self.title_style))
        story.append(Spacer(1, 0.3*inch))
        
        # 副标题
        story.append(Paragraph(f"{clean_filename}", self.subtitle_style))
        story.append(Spacer(1, 0.5*inch))
        
        # 文档信息
        info_style = ParagraphStyle(
            'InfoStyle',
            parent=self.subtitle_style,
            fontSize=11,
            alignment=TA_CENTER,
            spaceBefore=0.1*inch,
            spaceAfter=0.1*inch,
        )
        
        generation_date = datetime.now().strftime('%Y年%m月%d日')
        story.append(Paragraph(f"Generated on {generation_date}", info_style))
        story.append(Paragraph(f"生成日期：{generation_date}", info_style))
        story.append(Spacer(1, 0.2*inch))
        
        story.append(Paragraph(f"Translation Engine: {engine}", info_style))
        story.append(Paragraph(f"翻译引擎：{engine}", info_style))
        story.append(Spacer(1, 0.2*inch))
        
        story.append(Paragraph(f"Total Segments: {entry_count}", info_style))
        story.append(Paragraph(f"总段落数：{entry_count}", info_style))
        
        # 添加分页
        story.append(PageBreak())
    
    def _add_content(self, story, transcript_entries):
        """添加转录内容 - 只包含双语正文"""
        
        for i, entry in enumerate(transcript_entries, 1):
            # 添加英文原文
            english_text = self._clean_text(entry.get('original', ''))
            if english_text:
                story.append(Paragraph(english_text, self.english_style))
            
            # 添加中文翻译
            chinese_text = self._clean_text(entry.get('translation', ''))
            if chinese_text:
                story.append(Paragraph(chinese_text, self.chinese_style))
            
            # 在每个条目后添加小间距
            story.append(Spacer(1, 0.2*inch))
    
    def _clean_text(self, text):
        """清理和格式化文本"""
        if not text:
            return ""
        
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text.strip())
        
        # 转义HTML特殊字符
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        # 处理引号
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        
        return text
    
    def generate_summary_pdf(self, summary_text, original_filename, translation_engine):
        """生成内容摘要PDF"""
        # 创建输出文件名
        base_name = os.path.splitext(original_filename)[0]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"{base_name}_summary_{timestamp}.pdf"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # 创建PDF文档
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=1*inch,
            leftMargin=1*inch,
            topMargin=1*inch,
            bottomMargin=1*inch,
        )
        
        story = []
        
        # 标题
        story.append(Paragraph("Content Summary / 内容摘要", self.title_style))
        story.append(Spacer(1, 0.3*inch))
        
        # 文件信息
        story.append(Paragraph(f"Source: {original_filename}", self.subtitle_style))
        story.append(Paragraph(f"来源：{original_filename}", self.subtitle_style))
        story.append(Spacer(1, 0.3*inch))
        
        # 摘要内容
        cleaned_summary = self._clean_text(summary_text)
        story.append(Paragraph(cleaned_summary, self.chinese_style))
        
        # 生成PDF
        try:
            doc.build(story)
            return output_path
        except Exception as e:
            raise Exception(f"Summary PDF generation failed: {str(e)}")


def create_podcast_pdf(transcript_entries, original_filename, output_dir, translation_engine="OpenAI"):
    """便捷函数：创建播客PDF"""
    generator = PodcastPDFGenerator(output_dir)
    return generator.generate_pdf(transcript_entries, original_filename, translation_engine)


def create_summary_pdf(summary_text, original_filename, output_dir, translation_engine="OpenAI"):
    """便捷函数：创建摘要PDF"""
    generator = PodcastPDFGenerator(output_dir)
    return generator.generate_summary_pdf(summary_text, original_filename, translation_engine)
