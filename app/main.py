import psycopg2
from flask import Flask, jsonify, send_file, url_for, render_template_string
import os
import json
import zipfile
import logging

# create the Flask app
app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Function to create the stored function in the database
def create_select_function():
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST"),
        database=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASS"),
        port=os.environ.get("DB_PORT"),
    )
    with conn.cursor() as cur:
        create_function_query = """
        CREATE OR REPLACE FUNCTION select_tables_within_county(grid_value text)
        RETURNS TABLE(table_name text, record jsonb) AS $$
        DECLARE
            table_rec RECORD;
            sql_query text;
        BEGIN
            FOR table_rec IN 
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
                AND tablename != 'spatial_ref_sys'
            LOOP
                sql_query := format('
                    SELECT 
                        %L AS table_name,
                        jsonb_agg(
                            jsonb_build_object(
                                ''clipped_shape'', ST_AsGeoJSON(ST_Intersection(ST_Transform(t.shape, 4326), county.shape_4326))::jsonb,
                                ''properties'', to_jsonb(t) - ''shape''
                            )
                        ) AS record
                    FROM 
                        %I t
                    JOIN (
                        SELECT ST_Transform(shape, 4326) AS shape_4326 
                        FROM grd_50k
                        WHERE grd_50k.grid = %L
                        UNION ALL
                        SELECT ST_Transform(shape, 4326) AS shape_4326 
                        FROM grd
                        WHERE grd.grid = %L
                    ) county 
                    ON ST_Intersects(ST_Transform(t.shape, 4326), county.shape_4326)
                ', table_rec.tablename, table_rec.tablename, grid_value, grid_value);
        
                RETURN QUERY EXECUTE sql_query;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
        """
        cur.execute(create_function_query)
        conn.commit()
    conn.close()

# create the index route
@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>全臺地型圖資料庫下載</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #f4f4f9;
                margin: 0;
                padding: 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                text-align: center;
            }
            h1 {
                color: #333;
            }
            p {
                font-size: 1.2em;
                color: #666;
                max-width: 600px;
            }
            .container {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>全臺地型圖資料庫下載</h1>
            <p>此網頁提供之下載格式為 GeoJson，請<a href="https://github.com/TzuYu-Ma/cloudrun/tree/main">參照圖幅圖號或縣市代碼</a>，將所需圖號複製到網址欄後並按 Enter。</p>
            <p>例: 若需要 93203NW 地形圖資料，請在網址欄最右邊加上 "/93203NW"</p>
            <p>例: 若需要 屏東縣 地形圖資料，請在網址欄最右邊加上 "/10013"</p>
        </div>
    </body>
    </html>
    """)

# create a general DB to GeoJSON function based on a SQL query
def database_to_geojson_by_query(sql_query, grid):
    try:
        logging.debug(f"Executing SQL query: {sql_query}")
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST"),
            database=os.environ.get("DB_NAME"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASS"),
            port=os.environ.get("DB_PORT"),
        )
        with conn.cursor() as cur:
            cur.execute(sql_query)
            rows = cur.fetchall()
        conn.close()

        if not rows:
            logging.error(f"No rows returned for query: {sql_query}")
            return []

        geojson_files = []

        for row in rows:
            table_name = row[0]
            records = row[1]
            if not records:
                logging.warning(f"No records found for table: {table_name}")
                continue

            features = []

            for record in records:
                feature = {
                    "type": "Feature",
                    "geometry": record["shape"],
                    "properties": {k: v for k, v in record.items() if k != "shape"}
                }
                feature["properties"]["table_name"] = table_name
                features.append(feature)
            
            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            # Save each table's data into a separate GeoJSON file
            filename = f"{grid}_{table_name}.geojson"
            with open(filename, 'w') as f:
                json.dump(geojson, f)

            geojson_files.append(filename)

        return geojson_files

    except Exception as e:
        logging.error(f"Error in database_to_geojson_by_query: {e}")
        return []

# Route to generate and list GeoJSON files with download links
@app.route('/<grid>', methods=['GET'])
def get_json(grid):
    try:
        sql_query = f"SELECT * FROM select_tables_within_county('{grid}');"
        geojson_files = database_to_geojson_by_query(sql_query, grid)
        
        if not geojson_files:
            logging.error(f"No GeoJSON files generated for grid: {grid}")
            return "No GeoJSON files generated", 500

        # Generate download URLs for the files
        file_links = [{
            "name": os.path.splitext(filename)[0],
            "url": url_for('download_file', filename=filename, _external=True, _scheme='https')
        } for filename in geojson_files]

        # Generate HTML links for easy clicking
        html_links = ''.join([f'<li><a href="{file["url"]}">{file["name"]}</a></li>' for file in file_links])

        # Add link for downloading all files as a ZIP archive
        zip_url = url_for('download_all_files', grid=grid, _external=True, _scheme='https')
        zip_link = f'<li><a href="{zip_url}">Download All as ZIP</a></li>'

        # Return an HTML page with clickable links
        return render_template_string(f"""
        <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        background-color: #f4f4f9;
                        margin: 0;
                        padding: 20px;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        text-align: center;
                    }}
                    h1 {{
                        color: #333;
                    }}
                    ul {{
                        list-style: none;
                        padding: 0;
                    }}
                    li {{
                        margin: 10px 0;
                    }}
                    a {{
                        text-decoration: none;
                        color: #1a73e8;
                    }}
                    a:hover {{
                        text-decoration: underline;
                    }}
                    .container {{
                        background: white;
                        padding: 20px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Download GeoJSON Files</h1>
                    <ul>
                        {html_links}
                        {zip_link}
                    </ul>
                </div>
            </body>
        </html>
        """)
    except Exception as e:
        logging.error(f"Error in get_json: {e}")
        return "Internal Server Error", 500

# Route to download a specific GeoJSON file
@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_file(filename, as_attachment=True)

# Route to download all GeoJSON files as a ZIP archive
@app.route('/download_all/<grid>', methods=['GET'])
def download_all_files(grid):
    try:
        sql_query = f"SELECT * FROM select_tables_within_county('{grid}');"
        geojson_files = database_to_geojson_by_query(sql_query, grid)
        
        if not geojson_files:
            logging.error(f"No GeoJSON files to zip for grid: {grid}")
            return "No GeoJSON files to zip", 500

        zip_filename = f"{grid}_geojson_files.zip"
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            for geojson_file in geojson_files:
                zipf.write(geojson_file)
        
        return send_file(zip_filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Error in download_all_files: {e}")
        return "Internal Server Error", 500

if __name__ == "__main__":
    create_select_function()  # Create the function when the app starts
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
