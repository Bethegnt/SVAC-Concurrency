#!/usr/bin/env python3
"""
generate_tables_csv.py
======================
Generates structured CSV files for all tables in the SVAC-Concurrency paper.
Outputs to results/csvs/
"""

import os
import csv
import json

BASE = "/Users/bethegnt/Downloads/SVAC_Concurrency"
CSVS_DIR = os.path.join(BASE, "results", "csvs")
os.makedirs(CSVS_DIR, exist_ok=True)


def generate_table1():
    path = os.path.join(CSVS_DIR, "table1_cross_model.csv")
    rows = [
        ["Model Architecture", "Organization", "Scored (N)", "Parse Rate", "Step Acc (SA)", "Error Cascade (ECR)", "Verdict Acc (Parsed)", "Verdict Acc (All)"],
        ["Gemini-3.5-Flash-Lite", "Google DeepMind", "375 / 375", "99.2%", "56.1%", "36.9%", "72.8%", "72.3%"],
        ["OpenAI-GPT-OSS-20B", "OpenAI", "81 / 81", "58.0%", "53.1%", "45.3%", "100.0%", "58.0%"],
        ["Nemotron-3-Super-120B", "NVIDIA", "375 / 375", "19.7%", "48.5%", "41.3%", "95.9%", "18.9%"],
        ["Liquid-LFM-2.6B", "Liquid AI", "39 / 39", "69.2%", "14.4%", "86.1%", "96.3%", "66.7%"],
        ["Majority Baseline", "Random / Majority", "375 / 375", "100.0%", "0.0%", "100.0%", "50.0%", "50.0%"]
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Generated: {path}")


def generate_table2():
    path = os.path.join(CSVS_DIR, "table2_task_by_prompt_strategy.csv")
    rows = [
        ["Task Domain", "Zero-Shot (ZS)", "Few-Shot (FS)", "Chain-of-Thought (CoT)", "Task Mean SA"],
        ["WFG Deadlock Detection", "4.4%", "85.4%", "7.5%", "31.2%"],
        ["Banker's Safety Algorithm", "32.9%", "41.9%", "49.7%", "41.5%"],
        ["Buddy System Allocation", "30.5%", "31.5%", "49.1%", "36.9%"],
        ["Counting Semaphore Sync", "91.2%", "96.2%", "95.0%", "94.2%"],
        ["Mutex Lock Synchronization", "100.0%", "100.0%", "100.0%", "100.0%"],
        ["Non-Saturated Subset (WFG+Bankers+Buddy)", "22.6%", "52.9%", "35.4%", "37.0%"],
        ["Overall Suite Mean", "51.8%", "71.0%", "60.3%", "56.1%"]
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Generated: {path}")


def generate_table3():
    path = os.path.join(CSVS_DIR, "table3_wfg_error_taxonomy.csv")
    rows = [
        ["Error Metric / Category", "Zero-Shot (N=30)", "Few-Shot (N=30)", "Chain-of-Thought (N=30)"],
        ["Visited Set Corruption", "30 (100.0%)", "7 (23.3%)", "30 (100.0%)"],
        ["Recursion Stack Corruption", "14 (46.7%)", "12 (40.0%)", "8 (26.7%)"],
        ["Wrong Traversal Node", "20 (66.7%)", "12 (40.0%)", "18 (60.0%)"],
        ["Step Count Mismatch", "16 (53.3%)", "13 (43.3%)", "12 (40.0%)"],
        ["False Cycle Hallucination", "3 (10.0%)", "0 (0.0%)", "2 (6.7%)"],
        ["Missed Cycle (False Negative)", "0 (0.0%)", "0 (0.0%)", "0 (0.0%)"],
        ["Verdict Accuracy (VA)", "27 / 30 (90.0%)", "28 / 28 (100.0%)", "28 / 30 (93.3%)"],
        ["Strict Positional Step Accuracy", "4.4%", "85.4%", "7.5%"],
        ["Invariant-Based Valid Step Accuracy", "93.7%", "100.0%", "93.2%"]
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Generated: {path}")


def generate_table4():
    path = os.path.join(CSVS_DIR, "table4_invariant_vs_positional_sa.csv")
    rows = [
        ["Task Family / Variant", "Strict Positional SA", "Invariant-Based Valid SA", "Delta (Valid - Strict)"],
        ["Banker's Algorithm Overall (N=90)", "41.5%", "74.3%", "+32.8%"],
        ["  - Banker's Zero-Shot", "32.9%", "74.4%", "+41.6%"],
        ["  - Banker's Few-Shot", "41.9%", "78.9%", "+37.1%"],
        ["  - Banker's Chain-of-Thought", "49.7%", "69.5%", "+19.8%"],
        ["WFG Deadlock Overall (N=88)", "31.2%", "95.6%", "+64.3%"],
        ["  - WFG Zero-Shot", "4.4%", "93.7%", "+89.4%"],
        ["  - WFG Few-Shot", "85.4%", "100.0%", "+14.6%"],
        ["  - WFG Chain-of-Thought", "7.5%", "93.2%", "+85.8%"]
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Generated: {path}")


def generate_table5():
    path = os.path.join(CSVS_DIR, "table5_fep_distributions.csv")
    rows = [
        ["Task Domain", "Strategy", "Error Instances", "FEP=1 (%)", "Mean FEP", "Median FEP"],
        ["Banker's Algorithm", "Zero-Shot", "25", "76.0%", "1.28", "1.0"],
        ["Banker's Algorithm", "Few-Shot", "22", "59.1%", "1.55", "1.0"],
        ["Banker's Algorithm", "Chain-of-Thought", "17", "82.4%", "1.41", "1.0"],
        ["Buddy System Allocation", "Zero-Shot", "23", "34.8%", "6.96", "4.0"],
        ["Buddy System Allocation", "Few-Shot", "23", "26.1%", "7.57", "4.0"],
        ["Buddy System Allocation", "Chain-of-Thought", "22", "22.7%", "6.55", "5.0"],
        ["Counting Semaphore", "Zero-Shot", "3", "33.3%", "3.67", "3.0"],
        ["Counting Semaphore", "Few-Shot", "3", "0.0%", "4.33", "3.0"],
        ["Counting Semaphore", "Chain-of-Thought", "2", "0.0%", "3.00", "3.0"],
        ["WFG Deadlock Detection", "Zero-Shot", "30", "100.0%", "1.00", "1.0"],
        ["WFG Deadlock Detection", "Few-Shot", "13", "0.0%", "8.38", "7.0"],
        ["WFG Deadlock Detection", "Chain-of-Thought", "30", "100.0%", "1.00", "1.0"]
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Generated: {path}")


def main():
    print("=" * 60)
    print("Generating all CSV result tables for SVAC-Concurrency")
    print("=" * 60)
    generate_table1()
    generate_table2()
    generate_table3()
    generate_table4()
    generate_table5()
    print("All CSV tables generated in results/csvs/")


if __name__ == "__main__":
    main()
