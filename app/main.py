import psycopg2
from flask import Flask, jsonify, send_file, url_for, render_template_string, request, redirect
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
    try:
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
                        WITH county AS (
                            SELECT shape 
                            FROM grd_100k
                            WHERE grd_100k.grid = %L
                            UNION ALL
                            SELECT shape 
                            FROM grd_50k
                            WHERE grd_50k.grid = %L
                            UNION ALL
                            SELECT shape 
                            FROM grd_25k
                            WHERE grd_25k.grid = %L		
                            UNION ALL
                            SELECT shape 
                            FROM county_boundary
                            WHERE county_boundary.countycode = %L			
                        )
                        SELECT 
                            %L AS table_name,
                            jsonb_agg(t.*) AS record
                        FROM 
                            %I t
                        JOIN county 
                        ON ST_Intersects(t.shape, county.shape)
                        WHERE ST_IsValid(t.shape)
                    ', grid_value, grid_value, grid_value, grid_value, table_rec.tablename, table_rec.tablename);
            
                    RETURN QUERY EXECUTE sql_query;
                END LOOP;
            END;
            $$ LANGUAGE plpgsql;


            """
            cur.execute(create_function_query)
            conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error creating function: {e}")

# create the index route
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        grids_input = request.form['grid']
        grids = grids_input.split(',')
        return redirect(url_for('download_all_files_multiple', grids=",".join(grids)))
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>全臺地形圖資料庫下載</title>
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
            <h1>全臺地形圖資料庫下載</h1>
            <p>此網頁提供 GeoJSON 格式下載，請<a href="https://github.com/TzuYu-Ma/cloudrun/tree/main">參照圖幅圖號或縣市代碼</a>，將所需圖號、縣市代碼及向量名稱複製到網址欄後，按 Enter。</p>
            <p>或是請輸入多個圖號或縣市代碼，用逗號分隔，然後下載。</p>
            <form method="POST">
                <input type="text" name="grid" placeholder="輸入多個圖號或縣市代碼" required>
                <button type="submit">下載資料</button>
            </form>
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
                if 'shape' not in record:
                    logging.error(f"'shape' key not found in record: {record}")
                    continue
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
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        text-align: center;
                        overflow: hidden;
                    }}
                    h1 {{
                        color: #333;
                        margin-top: 0;
                    }}
                    ul {{
                        list-style: none;
                        padding: 0;
                        margin: 0;
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
                        max-width: 600px;
                        width: 100%;
                        box-sizing: border-box;
                        overflow-y: auto;
                        max-height: 100%;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Download GeoJSON Files</h1>
                    <ul>
                        {zip_link}
                        {html_links}
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
    try:
        return send_file(filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Error in download_file: {e}")
        return "File not found", 404

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
    
# Route to get GeoJSON data for a specific table within a given grid
@app.route('/<grid>/<table_name>', methods=['GET'])
def get_geojson_data(table_name, grid):
    try:
        sql_query = f"SELECT * FROM select_tables_within_county('{grid}');"
        geojson_files = database_to_geojson_by_query(sql_query, grid)
        
        if not geojson_files:
            logging.error(f"No GeoJSON files generated for grid: {grid}")
            return jsonify({"error": "No GeoJSON files generated"}), 500

        # Find the GeoJSON file for the specific table
        geojson_data = None
        for filename in geojson_files:
            if table_name in filename:
                with open(filename, 'r') as f:
                    geojson_data = json.load(f)
                break

        if not geojson_data:
            logging.error(f"No GeoJSON file found for table: {table_name} in grid: {grid}")
            return jsonify({"error": f"No GeoJSON file found for table: {table_name}"}), 404

        return jsonify(geojson_data)
    except Exception as e:
        logging.error(f"Error in get_geojson_data: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

if __name__ == "__main__":
    create_select_function()  # Create the function when the app starts
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
