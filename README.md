# Transformer Mean Temperature
Calculates mean temperature on a plot level for one or more IR (infrared) images

### Sample Docker Command line
Below is a sample command line that shows how the mean temperature Docker image could be run.
An explanation of the command line options used follows.
Be sure to read up on the [docker run](https://docs.docker.com/engine/reference/run/) command line for more information.

The files used in this example can be found on [Google Drive](https://drive.google.com/file/d/1WCv_JN4y_SZuEm_d89-B3KcvTtGKG7tT/view?usp=sharing).

```docker run --rm --mount "src=/home/test,target=/mnt,type=bind" -e "BETYDB_URL=https://terraref.ncsa.illinois.edu/bety/" -e "BETYDB_KEY=<key value>" agpipeline/meantemp:3.0 --working_space "/mnt" --metadata "/mnt/e475911c-3f79-4ebb-807f-f623d5ae7783_metadata_cleaned.json" --citation_author "Me Myself" --citation_title "Something that's warm" --citation_year "2019" "/mnt/ir_fullfield_L2_ua-mac_2018-07-07_stereovis_ir_sensors_partialplots_sorghum6_shade_flir_eastedge_mn.tif"```

This example command line assumes the source files are located in the `/home/test` folder of the local machine.
The name of the image to run is `agpipeline/meantemp:3.0`.

We are using the same folder for the source metadata and the cleaned metadata.
By using multiple `--mount` options, the source and output files can be separated.

**Docker commands** \
Everything between 'docker' and the name of the image are docker commands.

- `run` indicates we want to run an image
- `--rm` automatically delete the image instance after it's run
- `--mount "src=/home/test,target=/mnt,type=bind"` mounts the `/home/test` folder to the `/mnt` folder of the running image
- `-e "BETYDB_URL=https://terraref.ncsa.illinois.edu/bety/"` the URL to the BETYdb instance to fetch plot boundaries, and other data, from
- `-e "BETYDB_KEY=<key value>"` the key associated with the BETYdb URL (replace `<key value>` with value of your key)

We mount the `/home/test` folder to the running image to make available the file to the software in the image.

**Image's commands** \
The command line parameters after the image name are passed to the software inside the image.
Note that the paths provided are relative to the running image (see the --mount option specified above).

- `--working_space "/mnt"` specifies the folder to use as a workspace
- `--metadata "/mnt/e475911c-3f79-4ebb-807f-f623d5ae7783_metadata_cleaned.json"` is the name of the cleaned metadata
- `--citation_author "<author name>"` the name of the author to cite in the resulting CSV file(s)
- `--citation_title "<title>"` the title of the citation to store in the resulting CSV file(s)
- `--citation_year "<year>"` the year of the citation to store in the resulting CSV file(s)
- `"/mnt/ir_fullfield_L2_ua-mac_2018-07-07_stereovis_ir_sensors_partialplots_sorghum6_shade_flir_eastedge_mn.tif"` the name of one or more IR (infrared) image files to use when calculating plot-level mean temperature

