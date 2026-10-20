"""
Report Generator – Creates a comprehensive PDF mission report with all mission data.
Exports a mission folder containing PDF, CSV, images, and video reference.
"""
import os
import csv
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from PyQt5 import QtGui, QtCore

from utils.logger import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """
    Generates a comprehensive PDF mission report.
    Exports all mission data to a structured folder for judges.
    """
    def __init__(self, csv_filepath, image_archive, ai_data, graph_engine=None, video_filepath=None):
        self.csv_filepath = csv_filepath
        self.image_archive = image_archive
        self.ai_data = ai_data if isinstance(ai_data, dict) else {}
        self.graph_engine = graph_engine
        self.video_filepath = video_filepath

    def _safe_get(self, data, key, default=None):
        if isinstance(data, dict):
            return data.get(key, default)
        return default

    def _get_plot_image_bytesio(self):
        """Capture graph as in-memory PNG."""
        if not self.graph_engine:
            return None
        try:
            pixmap = self.graph_engine.plot_widget.grab()
            if pixmap.isNull():
                return None
            buffer = QtCore.QBuffer()
            buffer.open(QtCore.QIODevice.WriteOnly)
            if not pixmap.save(buffer, "PNG"):
                return None
            return BytesIO(buffer.data())
        except Exception as e:
            logger.error(f"Plot capture error: {e}")
            return None

    def _sample_images(self, camera, count=2):
        """Get up to `count` sample images from archive for a camera."""
        samples = []
        target_dir = self.image_archive._target_dir(camera) if self.image_archive else None
        if not target_dir or not os.path.exists(target_dir):
            return samples
        files = sorted([f for f in os.listdir(target_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))])
        # take evenly spaced samples
        step = max(1, len(files) // count)
        for i in range(0, min(len(files), count)):
            idx = min(i * step, len(files)-1)
            samples.append(os.path.join(target_dir, files[idx]))
        return samples

    def _extract_mission_summary(self):
        """Extract key metrics from CSV."""
        summary = {
            "Max Altitude": "-- m",
            "Min Pressure": "-- hPa",
            "Max Temperature": "-- °C",
            "Max Humidity": "-- %",
            "Battery Consumption": "-- V",
            "Max RPM": "--",
            "Mission Duration": "-- s",
            "Packet Loss": "-- %",
            "Max Velocity": "-- m/s",
            "Min Velocity": "-- m/s",
            "Average Descent Rate": "-- m/s",
            "Landing Coordinates": "--",
        }
        if not os.path.exists(self.csv_filepath):
            return summary
        try:
            import pandas as pd
            df = pd.read_csv(self.csv_filepath)
            if not df.empty:
                if 'ALTITUDE' in df.columns:
                    summary["Max Altitude"] = f"{df['ALTITUDE'].max():.1f} m"
                    # compute descent rate from altitude differences
                    alt_diff = df['ALTITUDE'].diff()
                    summary["Max Velocity"] = f"{abs(alt_diff).max():.1f} m/s"
                    summary["Min Velocity"] = f"{abs(alt_diff).min():.1f} m/s"
                    # Average descent rate during descent (where altitude decreasing)
                    descending = df[alt_diff < 0]
                    if not descending.empty:
                        avg_rate = abs(descending['ALTITUDE'].diff()).mean()
                        summary["Average Descent Rate"] = f"{avg_rate:.1f} m/s"
                if 'PRESSURE' in df.columns:
                    summary["Min Pressure"] = f"{df['PRESSURE'].min():.1f} hPa"
                if 'TEMP' in df.columns:
                    summary["Max Temperature"] = f"{df['TEMP'].max():.1f} °C"
                if 'HUMIDITY' in df.columns:
                    summary["Max Humidity"] = f"{df['HUMIDITY'].max():.1f} %"
                if 'VOLTAGE' in df.columns:
                    summary["Battery Consumption"] = f"{df['VOLTAGE'].min():.2f} V -> {df['VOLTAGE'].max():.2f} V"
                if 'ROTOR_RPM' in df.columns:
                    summary["Max RPM"] = f"{df['ROTOR_RPM'].max():.0f}"
                if 'TIME_STAMPING' in df.columns:
                    summary["Mission Duration"] = f"{len(df)} s"
                if 'GNSS_LATITUDE' in df.columns and 'GNSS_LONGITUDE' in df.columns:
                    lat = df['GNSS_LATITUDE'].iloc[-1]
                    lon = df['GNSS_LONGITUDE'].iloc[-1]
                    summary["Landing Coordinates"] = f"({lat:.5f}, {lon:.5f})"
        except Exception as e:
            logger.warning(f"CSV summary extraction failed: {e}")
        return summary

    def generate(self, output_dir=None, pdf_filename="Mission_Report.pdf"):
        """
        Generate the report and export mission folder.
        :param output_dir: directory to save all artifacts (if None, creates a dated folder)
        :param pdf_filename: name of the PDF file
        :return: path to the exported folder
        """
        # Determine output folder
        if output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join("mission_reports", f"mission_{timestamp}")
        os.makedirs(output_dir, exist_ok=True)

        # Copy CSV file to output folder
        csv_dest = os.path.join(output_dir, os.path.basename(self.csv_filepath))
        if os.path.exists(self.csv_filepath):
            shutil.copy2(self.csv_filepath, csv_dest)

        # Copy sample images
        for cam in ["atmospheric", "ground"]:
            cam_dir = os.path.join(output_dir, cam)
            os.makedirs(cam_dir, exist_ok=True)
            samples = self._sample_images(cam, count=4)
            for img_src in samples:
                shutil.copy2(img_src, cam_dir)

        # If video file provided, copy or create symlink
        video_dest = None
        if self.video_filepath and os.path.exists(self.video_filepath):
            video_ext = os.path.splitext(self.video_filepath)[1]
            video_dest = os.path.join(output_dir, f"mission_video{video_ext}")
            shutil.copy2(self.video_filepath, video_dest)

        # Generate PDF
        pdf_path = os.path.join(output_dir, pdf_filename)
        self._generate_pdf(pdf_path, output_dir)

        # Create a README.txt with file listing
        readme_path = os.path.join(output_dir, "README.txt")
        with open(readme_path, 'w') as f:
            f.write("Mission Report Artifacts\n")
            f.write("========================\n\n")
            f.write(f"Mission Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Team ID: 2026-INSPACe-CAN-7USAT-036\n\n")
            f.write("Files:\n")
            f.write(f"  - {os.path.basename(pdf_path)} : Full report\n")
            f.write(f"  - {os.path.basename(csv_dest)} : Raw telemetry data\n")
            f.write(f"  - atmospheric/ : Atmospheric camera images\n")
            f.write(f"  - ground/ : Ground camera images\n")
            if video_dest:
                f.write(f"  - {os.path.basename(video_dest)} : Mission video\n")

        logger.info(f"Mission report exported to: {output_dir}")
        return output_dir

    def _generate_pdf(self, pdf_path, output_dir):
        """Internal PDF generation."""
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=24, textColor=colors.blue)
        story.append(Paragraph("ANTRS Mission Report", title_style))
        story.append(Spacer(1, 0.3*inch))

        # Date and Team
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        story.append(Paragraph(f"Team: 2026-INSPACe-CAN-7USAT-036", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # 1. Mission Summary
        story.append(Paragraph("1. Mission Summary", styles['Heading2']))
        summary = self._extract_mission_summary()
        for key, val in summary.items():
            story.append(Paragraph(f"• {key}: {val}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # 2. AI Insights
        story.append(Paragraph("2. AI Insights", styles['Heading2']))
        ai_items = [
            ("Fingerprint", self._safe_get(self.ai_data, 'fingerprint', '--')),
            ("Wind", self._safe_get(self.ai_data, 'wind', {})),
            ("Landing Prediction", self._safe_get(self.ai_data, 'landing', '--')),
            ("Stability", self._safe_get(self.ai_data, 'stability', '--')),
            ("Recovery Health", self._safe_get(self.ai_data, 'recovery', '--')),
            ("Faults", self._safe_get(self.ai_data, 'faults', '--')),
        ]
        for label, value in ai_items:
            if isinstance(value, dict):
                val_str = f"{value.get('wind_speed_mps', '--')} m/s @ {value.get('wind_direction_deg', '--')}°"
            else:
                val_str = str(value)
            story.append(Paragraph(f"• {label}: {val_str}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # 3. Telemetry Graph
        story.append(Paragraph("3. Telemetry Graph", styles['Heading2']))
        img_bytesio = self._get_plot_image_bytesio()
        if img_bytesio:
            try:
                im = Image(img_bytesio, width=6*inch, height=4*inch)
                story.append(im)
            except Exception as e:
                story.append(Paragraph("Graph image unavailable.", styles['Normal']))
        else:
            story.append(Paragraph("No graph data available.", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # 4. Sample Images (Atmospheric & Ground)
        story.append(PageBreak())
        story.append(Paragraph("4. Sample Images", styles['Heading2']))
        for cam in ["atmospheric", "ground"]:
            story.append(Paragraph(f"4.{1 if cam=='atmospheric' else 2} {cam.capitalize()} Camera", styles['Heading3']))
            samples = self._sample_images(cam, count=2)
            if samples:
                # Arrange images in a row (max 2 per row)
                for i, img_path in enumerate(samples):
                    try:
                        img = Image(img_path, width=3*inch, height=2.5*inch)
                        story.append(img)
                        story.append(Paragraph(f"Image {i+1}", styles['Normal']))
                    except:
                        story.append(Paragraph(f"Image {i+1} could not be loaded.", styles['Normal']))
            else:
                story.append(Paragraph(f"No {cam} images available.", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))

        # 5. Video Reference (if available)
        if self.video_filepath and os.path.exists(self.video_filepath):
            story.append(PageBreak())
            story.append(Paragraph("5. Mission Video", styles['Heading2']))
            story.append(Paragraph(f"Video file: {os.path.basename(self.video_filepath)}", styles['Normal']))
            story.append(Paragraph(f"Location: {self.video_filepath}", styles['Normal']))

        # 6. CSV Data Appendix
        story.append(PageBreak())
        story.append(Paragraph("6. CSV Data Summary", styles['Heading2']))
        story.append(Paragraph("Full CSV data is available in the exported folder.", styles['Normal']))
        # Show first 10 rows
        if os.path.exists(self.csv_filepath):
            with open(self.csv_filepath, 'r') as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                rows = []
                for i, row in enumerate(reader):
                    if i >= 10:
                        break
                    rows.append(row)
                if headers and rows:
                    data = [headers] + rows
                    # Use landscape if many columns
                    col_width = 0.8*inch
                    table = Table(data, colWidths=[col_width]*len(headers))
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.grey),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 8),
                        ('BOTTOMPADDING', (0,0), (-1,0), 4),
                        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                    ]))
                    story.append(KeepTogether(table))
                else:
                    story.append(Paragraph("No CSV data.", styles['Normal']))

        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("End of Report", styles['Normal']))

        doc.build(story)
        logger.info(f"PDF report created: {pdf_path}")