def categorize_list(categorized_list: list, temp: list):
    normal_jobs = []
    special_jobs = []
    job_category_json = categorized_list

    if len(job_category_json) == len(temp):
        for index, item in enumerate(job_category_json):
            item["job_id"] = temp[index]["job_id"]
            item["job_categories"] = temp[index]["job_categories"]

        for item in job_category_json:
            if item["job_categories"] == "normal":
                normal_jobs.append(
                    item
                    # {

                    #     "job_id": item["job_id"],
                    #     "location": item["location"] ,
                    #     "component": item["component"] ,
                    #     "repair": item["repair"] ,
                    #     "damage": item["damage"] ,
                    #     "manhour": item["manhour"] ,
                    #     "labour_cost": item["labour_cost"] ,
                    #     "status": item["status"] ,
                    #     "cedex_code": item["cedex_code"] ,
                    #     "job_descripton": item["job_descripton"] ,
                    # }
                )
            else:
                special_jobs.append(item)
    else:
        raise ValueError(
            "Mismatch between extracted job count and categorized list count."
        )
    return {"normal_jobs": normal_jobs, "special_jobs": special_jobs}
