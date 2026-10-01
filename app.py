def parse_dashboard_html(html):
    soup = BeautifulSoup(html, "html.parser")
    data = {"profile": {}, "subjects": {}, "grand_total": None, "days": [], "analysis": {}}

    def extract_int(val_str):
        numbers = re.findall(r'\d+', val_str)
        return int(numbers[0]) if numbers else None

    # 1. Parse Profile Information
    for cell in soup.find_all(["td", "th", "div", "span"]):
        txt = text_of(cell)
        if ("Roll No" in txt or "HTNO" in txt or "PIN" in txt) and ":" in txt:
            data["profile"]["roll"] = txt.split(":")[-1].strip()
        elif ("Student" in txt or "Name" in txt) and ":" in txt:
            data["profile"]["name"] = txt.split(":")[-1].strip()

    all_rows = soup.find_all("tr")

    # 2. Dynamic Subject & Summary Scraping
    total_held_sum = 0
    total_present_sum = 0

    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        row_text = [text_of(c) for c in cells]
        combined_text = " ".join(row_text).lower()

        # Ignore header/navigation rows
        if any(kw in combined_text for kw in ["s.no", "sl.no", "subject name", "code", "percentage", "%"]):
            if "total" not in combined_text:
                continue

        # Find all numeric values across all columns in this row
        row_numbers = []
        subject_label = ""

        for idx, cell_txt in enumerate(row_text):
            num = extract_int(cell_txt)
            if num is not None:
                row_numbers.append(num)
            elif not subject_label and len(cell_txt) > 2:
                # Capture subject name from non-numeric text columns
                subject_label = cell_txt

        # Valid attendance entries usually have at least 2 numbers (Held & Attended)
        if len(row_numbers) >= 2:
            held = row_numbers[0]
            present = row_numbers[1]

            # Ensure valid numbers (Present cannot exceed Held)
            if present <= held and held > 0:
                if "total" in combined_text or "grand" in combined_text:
                    data["grand_total"] = {"held": held, "present": present}
                else:
                    if not subject_label:
                        subject_label = f"Subject {len(data['subjects']) + 1}"
                    
                    analysis = calculate_analysis(held, present)
                    data["subjects"][subject_label] = {
                        "held": held,
                        "present": present,
                        "pct": analysis["current_pct"],
                        "status": analysis["status"],
                        "margin_message": analysis["margin_message"]
                    }
                    total_held_sum += held
                    total_present_sum += present

    # Fallback for Grand Total if the table lacks an explicit Total row
    if not data["grand_total"] and total_held_sum > 0:
        data["grand_total"] = {"held": total_held_sum, "present": total_present_sum}

    # 3. Daily Attendance Extraction
    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        date_text = text_of(cells[0])
        if re.match(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}$", date_text):
            period_cells = [text_of(c).upper() for c in cells[1:-2]]
            periods = [p for p in period_cells if p in ("P", "A", "PRES", "ABS")]

            tot_val = extract_int(text_of(cells[-2]))
            att_val = extract_int(text_of(cells[-1]))

            data["days"].append({
                "date": date_text,
                "periods": periods,
                "total": tot_val if tot_val is not None else len(periods),
                "attend": att_val if att_val is not None else periods.count("P")
            })

    # Run overall calculation
    if data["grand_total"]:
        data["analysis"] = calculate_analysis(
            data["grand_total"]["held"],
            data["grand_total"]["present"]
        )

    return data
    
