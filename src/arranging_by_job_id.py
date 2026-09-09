import json


def arranging_by_id(jobs, special_job_dict):
    for items in special_job_dict:
        locations = items["location"]

        if not locations.endswith("XX"):

            locations = f"{locations}XX"

            cedex_code = (
                f'{locations} '
                f'{items["component"]} '
                f'{items["repair"]} '
                f'{items["damage"]}'
            )
            items["cedex_code"] = cedex_code

    successful_jobs = jobs["success_jobs"]
    failure_jobs = jobs["failed_jobs"]

    for items in successful_jobs:
        locations = items["location"]

        if ((items["status"] == "mapped") & (not locations.endswith("XX"))):
            cedex_code = (
                f'{items["location"]}XX '
                f'{items["component"]} '
                f'{items["repair"]} '
                f'{items["damage"]}'
            )

            items["cedex_code"] = cedex_code
    sum = len(successful_jobs) + len(failure_jobs) + len(special_job_dict)
    # all_jobs = successful_jobs.append(special_job_dict.append(failure_jobs))

    jobs_sorted = []
    # print("sum")
    # print(sum)

    for i in range(sum):
        for item in successful_jobs:
            if(item["job_id"]==i+1):
                jobs_sorted.append(item)
        for item in failure_jobs:
                if(item["job_id"]==i+1):
                    jobs_sorted.append(item)
        for item in special_job_dict:
                if(item["job_id"]==i+1):
                    jobs_sorted.append(item)

    return jobs_sorted
